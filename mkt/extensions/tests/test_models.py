# -*- coding: utf-8 -*-
import json
import mock
import os.path
from nose.tools import eq_, ok_

from django.conf import settings
from django.forms import ValidationError
from django.test.utils import override_settings

from lib.crypto.packaged import SigningError
from mkt.constants.base import (STATUS_NULL, STATUS_PENDING, STATUS_PUBLIC,
                                STATUS_REJECTED)
from mkt.extensions.models import Extension
from mkt.files.tests.test_models import UploadCreationMixin, UploadTest
from mkt.site.storage_utils import private_storage
from mkt.site.tests import fixture, TestCase
from mkt.users.models import UserProfile


class TestExtensionUpload(UploadCreationMixin, UploadTest):
    fixtures = fixture('user_2519')

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

    def setUp(self):
        super(TestExtensionUpload, self).setUp()
        self.user = UserProfile.objects.get(pk=2519)

    def create_extension(self, **kwargs):
        extension = Extension.objects.create(
            default_language='fr', version='0.9', manifest={}, **kwargs)
        return extension

    def test_auto_create_slug(self):
        extension = self.create_extension()
        eq_(extension.slug, 'extension')
        extension = self.create_extension()
        eq_(extension.slug, 'extension-1')
        extension = self.create_extension(name=u'Mŷ Ëxtension')
        eq_(extension.slug, u'mŷ-ëxtension')

    def test_auto_create_uuid(self):
        extension = self.create_extension()
        ok_(extension.uuid)
        extension2 = self.create_extension()
        ok_(extension.uuid != extension2.uuid)

    def test_upload_new(self):
        eq_(Extension.objects.count(), 0)
        upload = self.upload('extension')
        extension = Extension.from_upload(upload, user=self.user)
        eq_(extension.version, '0.1')
        eq_(list(extension.authors.all()), [self.user])
        eq_(extension.name, u'My Lîttle Extension')
        eq_(extension.default_language, 'en-GB')
        eq_(extension.slug, u'my-lîttle-extension')
        eq_(extension.filename, 'extension-%s.zip' % extension.version)
        ok_(extension.filename in extension.file_path)
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
        assert not private_storage.exists(filename)
        extension.delete()

    def test_delete_signal(self):
        """Test that the Extension instance can be deleted with the filename
        field being empty."""
        extension = Extension.objects.create()
        extension.delete()


class TestExtensionESIndexation(TestCase):
    @mock.patch('mkt.search.indexers.BaseIndexer.index_ids')
    def test_update_search_index(self, update_mock):
        extension = Extension.objects.create()
        update_mock.assert_called_once_with([extension.pk])

    @mock.patch('mkt.search.indexers.BaseIndexer.unindex')
    def test_delete_search_index(self, delete_mock):
        for x in xrange(3):
            Extension.objects.create()
        count = Extension.objects.count()
        eq_(count, 3)
        Extension.objects.all().delete()
        eq_(delete_mock.call_count, count)


class TestExtensionMethodsAndProperties(TestCase):
    @override_settings(SITE_URL='https://marketpace.example.com/')
    def test_download_url(self):
        extension = Extension(pk=41, version='0.41.0',
                              uuid='abcdef78123456781234567812345678')
        eq_(extension.download_url,
            'https://marketpace.example.com/downloads/extension/'
            'abcdef78123456781234567812345678/extension-0.41.0.zip')

    def test_file_paths(self):
        extension = Extension(pk=42, version='0.42.0')
        eq_(extension.filename, 'extension-0.42.0.zip')
        eq_(extension.file_path,
            os.path.join(settings.ADDONS_PATH, 'extensions', str(extension.pk),
                         extension.filename))
        eq_(extension.signed_file_path,
            os.path.join(settings.ADDONS_PATH, 'extensions-signed',
                         str(extension.pk), extension.filename))

    def test_file_version(self):
        # When we implement updates, change this test to test that the version
        # is increased when updates are added.
        eq_(Extension().file_version, 0)

    @override_settings(SITE_URL='https://marketpace.example.com/')
    def test_mini_manifest_url(self):
        extension = Extension(pk=43, version='0.43.0',
                              uuid='12345678123456781234567812abcdef')
        eq_(extension.mini_manifest_url,
            'https://marketpace.example.com/extension/'
            '12345678123456781234567812abcdef/manifest.json')

    def test_mini_manifest(self):
        manifest = {
            'author': 'Me',
            'description': 'Blah',
            'manifest_version': 2,
            'name': u'Ëxtension',
            'version': '0.44',
        }
        extension = Extension(pk=44, version='0.44.0', manifest=manifest,
                              uuid='abcdefabcdefabcdefabcdefabcdef12')
        expected_manifest = {
            'description': 'Blah',
            'developer': {
                'name': 'Me'
            },
            'name': u'Ëxtension',
            'package_path': extension.download_url,
            'version': '0.44',
        }
        eq_(extension.mini_manifest, expected_manifest)

        # Make sure that mini_manifest is a deepcopy.
        extension.mini_manifest['name'] = u'Faîl'
        eq_(extension.manifest['name'], u'Ëxtension')

    @mock.patch('mkt.extensions.models.sign_app')
    @mock.patch('mkt.extensions.models.private_storage')
    @mock.patch.object(Extension, 'remove_signed_file')
    def test_sign_and_move_file(self, remove_signed_file_mock,
                                private_storage_mock, sign_app_mock):
        extension = Extension(uuid='12345678123456781234567812345678')
        extension.sign_and_move_file()
        expected_args = (
            private_storage_mock.open.return_value,
            extension.signed_file_path,
            json.dumps({
                'id': extension.uuid,
                'version': 0
            })
        )
        eq_(sign_app_mock.call_args[0], expected_args)
        eq_(remove_signed_file_mock.call_count, 0)

    @mock.patch('mkt.extensions.models.sign_app')
    @mock.patch('mkt.extensions.models.private_storage')
    def test_sign_and_move_file_no_uuid(self, private_storage_mock,
                                        sign_app_mock):
        extension = Extension(uuid='')
        with self.assertRaises(SigningError):
            extension.sign_and_move_file()

    @mock.patch('mkt.extensions.models.sign_app')
    @mock.patch('mkt.extensions.models.private_storage')
    @mock.patch.object(Extension, 'remove_signed_file')
    def test_sign_and_move_file_error(self, remove_signed_file_mock,
                                      private_storage_mock, sign_app_mock):
        extension = Extension(uuid='12345678123456781234567812345678')
        sign_app_mock.side_effect = SigningError
        with self.assertRaises(SigningError):
            extension.sign_and_move_file()
        eq_(remove_signed_file_mock.call_count, 1)

    @mock.patch('mkt.extensions.models.public_storage')
    def test_remove_signed_file(self, mocked_public_storage):
        extension = Extension(pk=42, slug='mocked_ext')
        mocked_public_storage.exists.return_value = True
        extension.remove_signed_file()
        eq_(mocked_public_storage.exists.call_args[0][0],
            extension.signed_file_path)
        eq_(mocked_public_storage.delete.call_args[0][0],
            extension.signed_file_path)

    @mock.patch('mkt.extensions.models.public_storage')
    def test_remove_signed_file_not_exists(self, public_storage_mock):
        extension = Extension(pk=42, slug='mocked_ext')
        public_storage_mock.exists.return_value = False
        extension.remove_signed_file()
        eq_(public_storage_mock.exists.call_args[0][0],
            extension.signed_file_path)
        eq_(public_storage_mock.delete.call_count, 0)

    @mock.patch.object(Extension, 'sign_and_move_file')
    def test_publish(self, mocked_sign_and_move_file):
        extension = Extension.objects.create()
        eq_(extension.status, STATUS_NULL)
        extension.publish()
        eq_(mocked_sign_and_move_file.call_count, 1)
        extension = Extension.objects.get(pk=extension.pk)
        eq_(extension.status, STATUS_PUBLIC)

    @mock.patch.object(Extension, 'remove_signed_file')
    def test_reject(self, mocked_remove_signed_file):
        extension = Extension.objects.create()
        eq_(extension.status, STATUS_NULL)
        extension.reject()
        eq_(mocked_remove_signed_file.call_count, 1)
        extension = Extension.objects.get(pk=extension.pk)
        eq_(extension.status, STATUS_REJECTED)


class TestExtensionManager(TestCase):
    def test_pending(self):
        extension1 = Extension.objects.create(status=STATUS_PENDING)
        extension2 = Extension.objects.create(status=STATUS_PENDING)
        Extension.objects.create(status=STATUS_PUBLIC)
        Extension.objects.create(status=STATUS_NULL)

        eq_(list(Extension.objects.pending()), [extension1, extension2])
