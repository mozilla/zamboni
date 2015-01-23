# -*- coding: utf-8 -*-
import json
import os

from django.core.files.storage import default_storage as storage
from django.forms import ValidationError

from mock import patch
from nose.tools import eq_, ok_

from mkt.files.helpers import copyfileobj
from mkt.files.models import FileUpload, nfd_str
from mkt.files.tests.test_models import UploadTest
from mkt.langpacks.models import LangPack
from mkt.site.tests import TestCase


class TestLangPackUpload(UploadTest):
    def upload(self, name):
        if os.path.splitext(name)[-1] not in ['.webapp', '.zip']:
            name = name + '.zip'

        v = json.dumps(dict(errors=0, warnings=1, notices=2, metadata={}))
        fname = nfd_str(self.packaged_app_path(name))
        if not storage.exists(fname):
            with storage.open(fname, 'w') as fs:
                copyfileobj(open(fname), fs)
        d = dict(path=fname, name=name,
                 hash='sha256:%s' % name, validation=v)
        return FileUpload.objects.create(**d)

    def test_upload_new(self):
        eq_(LangPack.objects.count(), 0)
        upload = self.upload('langpack')
        langpack = LangPack.from_upload(upload)
        ok_(langpack.uuid)
        eq_(langpack.version, '1.0.3')
        eq_(langpack.language, 'de')
        eq_(langpack.fxos_version, '2.2')
        eq_(langpack.filename, '%s-%s.zip' % (langpack.uuid, langpack.version))
        ok_(langpack.filename in langpack.file_path)
        ok_(os.path.exists(langpack.file_path))
        eq_(langpack.hash[0:23], 'sha256:f0fa5a4f5c0edf2d')
        eq_(langpack.size, 499)
        ok_(LangPack.objects.no_cache().get(pk=langpack.uuid))
        eq_(LangPack.objects.count(), 1)
        return langpack

    def test_upload_existing(self):
        langpack = self.test_upload_new()
        uuid = langpack.uuid
        langpack.hash = 'fakehash'
        langpack.size = 0
        langpack.language = 'fr'
        langpack.version = '0.9'
        langpack.fxos_version = '2.1'
        langpack.active = False
        langpack.save()
        upload = self.upload('langpack')
        langpack = LangPack.from_upload(upload, instance=langpack)
        eq_(langpack.uuid, uuid)
        eq_(langpack.version, '1.0.3')
        eq_(langpack.language, 'de')
        eq_(langpack.fxos_version, '2.2')
        eq_(langpack.filename, '%s-%s.zip' % (langpack.uuid, langpack.version))
        ok_(langpack.filename in langpack.file_path)
        ok_(os.path.exists(langpack.file_path))
        eq_(langpack.hash[0:23], 'sha256:f0fa5a4f5c0edf2d')
        eq_(langpack.size, 499)
        ok_(LangPack.objects.no_cache().get(pk=langpack.uuid))
        eq_(LangPack.objects.count(), 1)

    @patch('mkt.files.utils.WebAppParser.get_json_data')
    def test_upload_language_validation(self, get_json_data_mock):
        upload = self.upload('langpack')
        get_json_data_mock.return_value = {
            'role': 'langpack',
            'languages-provided': {
                'es': {}
            },
            'languages-target': {
                'app://*.gaiamobile.org/manifest.webapp': '2.2'
            }
        }
        ok_(LangPack.from_upload(upload))
        get_json_data_mock.return_value['languages-provided'] = {
            'invalid-lang': {}
        }
        expected = [u"Value 'invalid-lang' is not a valid choice."]
        with self.assertRaises(ValidationError) as e:
            LangPack.from_upload(upload)
        eq_(e.exception.messages, expected)


class TestLangPackDeletion(TestCase):
    def test_delete_with_file(self):
        """Test that when a LangPack instance is deleted, the corresponding
        file on the filesystem is also deleted."""
        langpack = LangPack.objects.create(filename='temporary-file.zip')
        file_path = langpack.file_path
        with storage.open(file_path, 'w') as f:
            f.write('sample data\n')
        assert storage.exists(file_path)
        try:
            langpack.delete()
            assert not storage.exists(file_path)
        finally:
            if storage.exists(file_path):
                storage.delete(file_path)

    def test_delete_no_file(self):
        """Test that the LangPack instance can be deleted without the file
        being present."""
        langpack = LangPack.objects.create(filename='should-not-exist.zip')
        filename = langpack.file_path
        assert not os.path.exists(filename), 'File exists at: %s' % filename
        langpack.delete()

    def test_delete_signal(self):
        """Test that the LangPack instance can be deleted with the filename
        field being empty."""
        langpack = LangPack.objects.create()
        langpack.delete()
