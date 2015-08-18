# -*- coding: utf-8 -*-
import mock
from nose.tools import eq_, ok_

from django.forms import ValidationError

from mkt.extensions.models import Extension
from mkt.files.tests.test_models import UploadCreationMixin, UploadTest
from mkt.site.storage_utils import private_storage
from mkt.site.tests import TestCase


class TestExtensionUpload(UploadCreationMixin, UploadTest):
    # Expected manifest, to test zip file parsing.
    expected_manifest = {
        'description': u'A Dummÿ Extension',
        'default_locale': 'en_GB',
        'icons': {
            '128': '/icon.png'
        },
        'version': '0.1',
        'author': 'Mozilla',
        'name': u'My Lîttle Extension'
    }

    def create_extension(self):
        extension = Extension.objects.create(
            default_language='fr', version='0.9', manifest={})
        return extension

    def test_upload_new(self):
        eq_(Extension.objects.count(), 0)
        upload = self.upload('extension')
        extension = Extension.from_upload(upload)
        eq_(extension.version, '0.1')
        eq_(extension.name, u'My Lîttle Extension')
        eq_(extension.default_language, 'en-GB')
        eq_(extension.slug, u'my-lîttle-extension')
        eq_(extension.filename, 'extension-%s.zip' % extension.version)
        ok_(extension.filename in extension.file_path)
        ok_(extension.file_path.startswith(extension.path_prefix))
        ok_(private_storage.exists(extension.file_path))
        eq_(extension.manifest, self.expected_manifest)
        eq_(Extension.objects.count(), 1)

    @mock.patch('mkt.extensions.utils.ExtensionParser.manifest_contents')
    def test_upload_no_version(self, manifest_mock):
        manifest_mock.__get__ = mock.Mock(return_value={'name': 'lol'})
        upload = self.upload('extension')
        with self.assertRaises(ValidationError):
            Extension.from_upload(upload)

    @mock.patch('mkt.extensions.utils.ExtensionParser.manifest_contents')
    def test_upload_no_name(self, manifest_mock):
        manifest_mock.__get__ = mock.Mock(return_value={'version': '0.1'})
        upload = self.upload('extension')
        with self.assertRaises(ValidationError):
            Extension.from_upload(upload)

    def test_upload_existing(self):
        extension = self.create_extension()
        upload = self.upload('extension')
        with self.assertRaises(NotImplementedError):
            Extension.from_upload(upload, instance=extension)


class TestExtensionDeletion(TestCase):
    def test_delete_with_file(self):
        """Test that when a Extension instance is deleted, the corresponding
        file on the filesystem is also deleted."""
        extension = Extension.objects.create(version='0.1')
        file_path = extension.file_path
        with private_storage.open(file_path, 'w') as f:
            f.write('sample data\n')
        assert private_storage.exists(file_path)
        try:
            extension.delete()
            assert not private_storage.exists(file_path)
        finally:
            if private_storage.exists(file_path):
                private_storage.delete(file_path)

    def test_delete_no_file(self):
        """Test that the Extension instance can be deleted without the file
        being present."""
        extension = Extension.objects.create(version='0.1')
        filename = extension.file_path
        assert (not private_storage.exists(filename),
                'File exists at: %s' % filename)
        extension.delete()

    def test_delete_signal(self):
        """Test that the Extension instance can be deleted with the filename
        field being empty."""
        extension = Extension.objects.create()
        extension.delete()
