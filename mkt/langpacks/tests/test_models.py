# -*- coding: utf-8 -*-
import json
import os

from django.core.files.storage import default_storage as storage
from django.forms import ValidationError

from mock import patch
from nose.tools import eq_, ok_

from lib.crypto.packaged import SigningError
from mkt.files.helpers import copyfileobj
from mkt.files.models import FileUpload, nfd_str
from mkt.files.tests.test_models import UploadTest
from mkt.langpacks.models import LangPack
from mkt.site.tests import TestCase


class UploadCreationMixin(object):
    def upload(self, name, **kwargs):
        if os.path.splitext(name)[-1] not in ['.webapp', '.zip']:
            name = name + '.zip'

        v = json.dumps(dict(errors=0, warnings=1, notices=2, metadata={}))
        fname = nfd_str(self.packaged_app_path(name))
        if not storage.exists(fname):
            with storage.open(fname, 'w') as fs:
                copyfileobj(open(fname), fs)
        data = {
            'path': fname,
            'name': name,
            'hash': 'sha256:%s' % name,
            'validation': v
        }
        data.update(**kwargs)
        return FileUpload.objects.create(**data)


class TestLangPackUpload(UploadTest, UploadCreationMixin):
    def create_langpack(self):
        langpack = LangPack.objects.create(
            hash='fakehash', size=1, language='fr', version='0.9',
            fxos_version='2.1', active=False, file_version=1)
        langpack.generate_filename()
        langpack.save()
        return langpack

    def test_upload_new(self):
        eq_(LangPack.objects.count(), 0)
        upload = self.upload('langpack')
        langpack = LangPack.from_upload(upload)
        ok_(langpack.uuid)
        eq_(langpack.file_version, 1)
        eq_(langpack.version, '1.0.3')
        eq_(langpack.language, 'de')
        eq_(langpack.fxos_version, '2.2')
        eq_(langpack.filename, '%s-%s.zip' % (langpack.uuid, langpack.version))
        ok_(langpack.filename in langpack.file_path)
        ok_(langpack.file_path.startswith(langpack.path_prefix))
        ok_(os.path.exists(langpack.file_path))
        eq_(langpack.hash[0:23], 'sha256:f0fa5a4f5c0edf2d')
        eq_(langpack.size, 499)
        ok_(LangPack.objects.no_cache().get(pk=langpack.uuid))
        eq_(LangPack.objects.count(), 1)
        return langpack

    def test_upload_existing(self):
        langpack = self.create_langpack()
        original_uuid = langpack.uuid
        original_file_path = langpack.file_path
        original_file_version = langpack.file_version
        upload = self.upload('langpack')
        langpack = LangPack.from_upload(upload, instance=langpack)
        eq_(langpack.uuid, original_uuid)
        eq_(langpack.version, '1.0.3')
        eq_(langpack.language, 'de')
        eq_(langpack.fxos_version, '2.2')
        eq_(langpack.filename, '%s-%s.zip' % (langpack.uuid, langpack.version))
        ok_(langpack.file_path.startswith(langpack.path_prefix))
        ok_(langpack.filename in langpack.file_path)
        ok_(langpack.file_path != original_file_path)
        ok_(langpack.file_version > original_file_version)
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
            },
            'version': '0.1'
        }
        ok_(LangPack.from_upload(upload))
        get_json_data_mock.return_value['languages-provided'] = {
            'invalid-lang': {}
        }
        expected = [u"Value 'invalid-lang' is not a valid choice."]
        with self.assertRaises(ValidationError) as e:
            LangPack.from_upload(upload)
        eq_(e.exception.messages, expected)

    @patch('mkt.files.utils.WebAppParser.get_json_data')
    def test_upload_version_missing(self, get_json_data_mock):
        upload = self.upload('langpack')
        get_json_data_mock.return_value = {
            'role': 'langpack',
            'languages-provided': {
                'es': {}
            },
            'languages-target': {
                'app://*.gaiamobile.org/manifest.webapp': '2.2'
            },
        }
        expected = [u'Your language pack should contain a version.']
        with self.assertRaises(ValidationError) as e:
            LangPack.from_upload(upload)
        eq_(e.exception.messages, expected)

    @patch('mkt.files.utils.WebAppParser.get_json_data')
    def test_upload_existing_same_version(self, get_json_data_mock):
        upload = self.upload('langpack')
        langpack = self.create_langpack()
        get_json_data_mock.return_value = {
            'role': 'langpack',
            'languages-provided': {
                'es': {}
            },
            'languages-target': {
                'app://*.gaiamobile.org/manifest.webapp': '2.2'
            },
            'version': '1.0'
        }
        # Works once.
        ok_(LangPack.from_upload(upload, instance=langpack))

        # Doesn't work twice, since we are re-uploading the same version.
        expected = [u'Your language pack version must be different to the one '
                    u'you are replacing.']
        with self.assertRaises(ValidationError) as e:
            LangPack.from_upload(upload, instance=langpack)
        eq_(e.exception.messages, expected)

    @patch('mkt.langpacks.models.sign_app')
    def test_upload_sign(self, sign_app_mock):
        eq_(LangPack.objects.count(), 0)
        upload = self.upload('langpack')
        langpack = LangPack.from_upload(upload)
        ok_(langpack.pk)
        ok_(langpack.file_version)
        ok_(langpack.file_path)
        eq_(LangPack.objects.count(), 1)
        expected_args = (
            upload.path,
            langpack.file_path,
            json.dumps({'id': langpack.pk, 'version': langpack.file_version})
        )
        sign_app_mock.assert_called_once_with(*expected_args)

    @patch('mkt.langpacks.models.sign_app')
    def test_upload_sign_existing(self, sign_app_mock):
        langpack = self.create_langpack()
        eq_(LangPack.objects.count(), 1)
        upload = self.upload('langpack')
        langpack = LangPack.from_upload(upload, instance=langpack)
        ok_(langpack.pk)
        ok_(langpack.file_version)
        ok_(langpack.file_path)
        eq_(LangPack.objects.count(), 1)
        expected_args = (
            upload.path,
            langpack.file_path,
            json.dumps({'id': langpack.pk, 'version': langpack.file_version})
        )
        sign_app_mock.assert_called_once_with(*expected_args)

    @patch('mkt.langpacks.models.sign_app')
    def test_upload_sign_error(self, sign_app_mock):
        sign_app_mock.side_effect = SigningError
        eq_(LangPack.objects.count(), 0)
        upload = self.upload('langpack')
        with self.assertRaises(SigningError):
            LangPack.from_upload(upload)
        # Test that we didn't delete the upload file
        ok_(storage.exists(upload.path))

    @patch('mkt.langpacks.models.sign_app')
    def test_upload_sign_error_existing(self, sign_app_mock):
        sign_app_mock.side_effect = SigningError
        langpack = self.create_langpack()
        eq_(LangPack.objects.count(), 1)
        original_uuid = langpack.uuid
        original_file_path = langpack.file_path
        original_file_version = langpack.file_version
        original_version = langpack.version
        # create_langpack() doesn't create a fake file, let's add one.
        storage.open(langpack.file_path, 'w').close()

        upload = self.upload('langpack')
        with self.assertRaises(SigningError):
            LangPack.from_upload(upload, instance=langpack)
        # Test that we didn't delete the upload file
        ok_(storage.exists(upload.path))
        # Test that we didn't delete the existing filename or alter the
        # existing langpack in the database.
        eq_(LangPack.objects.count(), 1)
        langpack.reload()
        eq_(original_uuid, langpack.uuid)
        eq_(langpack.file_path, original_file_path)
        eq_(original_file_version, langpack.file_version)
        eq_(original_version, langpack.version)
        ok_(storage.exists(langpack.file_path))

        # Cleanup
        storage.delete(langpack.file_path)


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
