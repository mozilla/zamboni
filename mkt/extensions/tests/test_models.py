# -*- coding: utf-8 -*-
import json
import mock
import os.path

from django.conf import settings
from django.test.utils import override_settings

from nose.tools import eq_, ok_
from rest_framework.exceptions import ParseError

from lib.crypto.packaged import SigningError
from mkt.constants.base import (STATUS_DISABLED, STATUS_NULL, STATUS_PENDING,
                                STATUS_PUBLIC, STATUS_REJECTED)
from mkt.extensions.models import Extension, ExtensionVersion
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

    def test_auto_create_slug(self):
        extension = Extension.objects.create()
        eq_(extension.slug, 'extension')
        extension = Extension.objects.create()
        eq_(extension.slug, 'extension-1')
        extension = Extension.objects.create(name=u'Mŷ Ëxtension')
        eq_(extension.slug, u'mŷ-ëxtension')

    def test_auto_create_uuid(self):
        extension = Extension.objects.create()
        ok_(extension.uuid)
        extension2 = Extension.objects.create()
        ok_(extension.uuid != extension2.uuid)

    def test_upload_new(self):
        eq_(Extension.objects.count(), 0)
        upload = self.upload('extension')
        extension = Extension.from_upload(upload, user=self.user)
        ok_(extension.pk)
        eq_(extension.latest_version, ExtensionVersion.objects.latest('pk'))
        eq_(Extension.objects.count(), 1)
        eq_(ExtensionVersion.objects.count(), 1)

        eq_(list(extension.authors.all()), [self.user])
        eq_(extension.name, u'My Lîttle Extension')
        eq_(extension.default_language, 'en-GB')
        eq_(extension.description, u'A Dummÿ Extension')
        eq_(extension.slug, u'my-lîttle-extension')
        eq_(extension.status, STATUS_PENDING)
        ok_(extension.uuid)

        version = extension.latest_version
        eq_(version.version, '0.1')
        eq_(version.default_language, 'en-GB')
        eq_(version.filename, 'extension-%s.zip' % version.version)
        ok_(version.filename in version.file_path)
        ok_(private_storage.exists(version.file_path))
        eq_(version.manifest, self.expected_manifest)

    @mock.patch('mkt.extensions.models.ExtensionValidator.validate_json')
    def test_upload_no_version(self, validate_mock):
        validate_mock.return_value = {'name': 'lol'}
        upload = self.upload('extension')
        with self.assertRaises(ParseError):
            Extension.from_upload(upload, user=self.user)

    @mock.patch('mkt.extensions.models.ExtensionValidator.validate_json')
    def test_upload_no_name(self, validate_mock):
        validate_mock.return_value = {'version': '0.1'}
        upload = self.upload('extension')
        with self.assertRaises(ParseError):
            Extension.from_upload(upload, user=self.user)

    def test_upload_new_version(self):
        extension = Extension.objects.create()
        old_version = ExtensionVersion.objects.create(
            extension=extension, version='0.0')
        eq_(extension.latest_version, old_version)
        eq_(extension.status, STATUS_NULL)
        upload = self.upload('extension')
        # Instead of calling Extension.from_upload(), we need to call
        # ExtensionVersion.from_upload() directly, since an Extension already
        # exists.
        version = ExtensionVersion.from_upload(upload, parent=extension)

        eq_(extension.latest_version, version)
        eq_(extension.status, STATUS_PENDING)

        eq_(version.version, '0.1')
        eq_(version.default_language, 'en-GB')
        eq_(version.filename, 'extension-%s.zip' % version.version)
        ok_(version.filename in version.file_path)
        ok_(private_storage.exists(version.file_path))
        eq_(version.manifest, self.expected_manifest)
        eq_(version.status, STATUS_PENDING)

    def test_upload_new_version_existing_pending_are_rendered_obsolete(self):
        extension = Extension.objects.create()
        older_version = ExtensionVersion.objects.create(
            extension=extension, version='0.0.0', status=STATUS_PENDING)
        old_version = ExtensionVersion.objects.create(
            extension=extension, version='0.0', status=STATUS_PENDING)
        eq_(extension.latest_version, old_version)
        eq_(extension.status, STATUS_PENDING)
        upload = self.upload('extension')
        # Instead of calling Extension.from_upload(), we need to call
        # ExtensionVersion.from_upload() directly, since an Extension already
        # exists.
        version = ExtensionVersion.from_upload(upload, parent=extension)

        eq_(extension.latest_version, version)
        eq_(extension.status, STATUS_PENDING)
        eq_(version.status, STATUS_PENDING)
        old_version.reload()
        older_version.reload()
        eq_(old_version.status, STATUS_DISABLED)
        eq_(older_version.status, STATUS_DISABLED)

    def test_upload_new_version_other_extension_are_not_affected(self):
        other_extension = Extension.objects.create()
        other_version = ExtensionVersion.objects.create(
            extension=other_extension, version='0.0', status=STATUS_PENDING)
        eq_(other_extension.status, STATUS_PENDING)
        eq_(other_version.status, STATUS_PENDING)
        self.test_upload_new_version_existing_pending_are_rendered_obsolete()
        other_extension.reload()
        other_version.reload()
        # other_extension and other_version should not have been affected.
        eq_(other_extension.status, STATUS_PENDING)
        eq_(other_version.status, STATUS_PENDING)

    def test_upload_new_version_existing_version(self):
        extension = Extension.objects.create()
        ExtensionVersion.objects.create(extension=extension, version='0.1')
        ExtensionVersion.objects.create(extension=extension, version='0.2.0')
        upload = self.upload('extension')  # Also uses version "0.1".
        with self.assertRaises(ParseError):
            ExtensionVersion.from_upload(upload, parent=extension)

    def test_upload_new_version_existing_version_number_is_higher(self):
        extension = Extension.objects.create()
        ExtensionVersion.objects.create(extension=extension, version='0.2')
        upload = self.upload('extension')
        with self.assertRaises(ParseError):
            # Try to upload version 0.1 it should fail since 0.2 is the latest.
            ExtensionVersion.from_upload(upload, parent=extension)

    def test_upload_new_version_no_parent(self):
        upload = self.upload('extension')
        with self.assertRaises(ValueError):
            ExtensionVersion.from_upload(upload)


class TestExtensionVersionDeletion(TestCase):
    def test_delete_with_file(self):
        """Test that when a Extension instance is deleted, the ExtensionVersion
        referencing it are also deleted, as well as the attached files."""
        extension = Extension.objects.create()
        version = ExtensionVersion.objects.create(
            extension=extension, version='0.1')
        file_path = version.file_path
        with private_storage.open(file_path, 'w') as f:
            f.write('sample data\n')
        assert private_storage.exists(file_path)
        try:
            extension.delete()
            assert not Extension.objects.count()
            assert not ExtensionVersion.objects.count()
            assert not private_storage.exists(file_path)
        finally:
            if private_storage.exists(file_path):
                private_storage.delete(file_path)

    def test_delete_no_file(self):
        """Test that the ExtensionVersion instance can be deleted without the
        file being present."""
        extension = Extension.objects.create()
        version = ExtensionVersion.objects.create(
            extension=extension, version='0.1')
        filename = version.file_path
        assert not private_storage.exists(filename)
        extension.delete()

    def test_delete_empty_filename(self):
        """Test that the ExtensionVersion instance can be deleted with the
        filename field being empty."""
        extension = Extension.objects.create()
        version = ExtensionVersion.objects.create(extension=extension)
        version.delete()

    @mock.patch.object(Extension, 'update_status_according_to_versions')
    def test_status_update_on_deletion(self, update_status_mock):
        """Test that when an ExtensionVersion is deleted, we call
        update_status_according_to_versions() on the Extension."""
        extension = Extension.objects.create()
        version = ExtensionVersion.objects.create(extension=extension)
        update_status_mock.reset_mock()
        eq_(update_status_mock.call_count, 0)
        version.delete()
        eq_(update_status_mock.call_count, 1)


class TestExtensionESIndexation(TestCase):
    @mock.patch('mkt.search.indexers.BaseIndexer.index_ids')
    def test_update_search_index(self, index_ids_mock):
        extension = Extension.objects.create()
        index_ids_mock.assert_called_once_with([extension.pk])

    @mock.patch('mkt.search.indexers.BaseIndexer.unindex')
    def test_delete_search_index(self, unindex_mock):
        for x in xrange(3):
            Extension.objects.create()
        count = Extension.objects.count()
        eq_(count, 3)
        Extension.objects.all().delete()
        eq_(unindex_mock.call_count, count)


class TestExtensionStatusChanges(TestCase):
    def test_new_version_null(self):
        extension = Extension.objects.create()
        eq_(extension.status, STATUS_NULL)
        version = ExtensionVersion.objects.create(extension=extension)
        eq_(extension.status, STATUS_NULL)
        eq_(version.status, STATUS_NULL)

    def test_new_version_pending(self):
        extension = Extension.objects.create()
        eq_(extension.status, STATUS_NULL)
        version = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PENDING, version='0.1')
        eq_(extension.status, STATUS_PENDING)
        eq_(extension.latest_version, version)

        new_version = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PENDING, version='0.2')
        extension.reload()
        eq_(extension.status, STATUS_PENDING)
        eq_(extension.latest_version, new_version)

    def test_extension_pending_version_deleted(self):
        extension = Extension.objects.create()
        new_version = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PENDING, version='0.1')
        eq_(extension.status, STATUS_PENDING)
        eq_(extension.latest_version, new_version)
        new_version.delete()
        eq_(extension.status, STATUS_NULL)
        with self.assertRaises(ExtensionVersion.DoesNotExist):
            extension.latest_version

    def test_pending_version_deleted_fallback_to_other(self):
        extension = Extension.objects.create()
        old_version = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PENDING, version='0.1')
        new_version = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PENDING, version='0.2')
        eq_(extension.status, STATUS_PENDING)
        eq_(extension.latest_version, new_version)
        new_version.delete()
        eq_(extension.status, STATUS_PENDING)
        eq_(extension.latest_version, old_version)
        extension.reload()
        eq_(extension.status, STATUS_PENDING)
        eq_(extension.latest_version, old_version)

    def test_public_extension_pending_version_deleted_no_change(self):
        extension = Extension.objects.create()
        old_version = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PENDING, version='0.1')
        new_version = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PENDING, version='0.2')
        eq_(extension.status, STATUS_PENDING)
        eq_(extension.latest_version, new_version)
        new_version.delete()
        eq_(extension.latest_version, old_version)
        extension.reload()
        eq_(extension.status, STATUS_PENDING)
        eq_(extension.latest_version, old_version)

    def test_new_version_public(self):
        extension = Extension.objects.create()
        ExtensionVersion.objects.create(
            extension=extension, status=STATUS_NULL, version='0.1')
        new_public_version = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PUBLIC, version='0.2')
        new_pending_version = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PENDING, version='0.3')
        eq_(extension.status, STATUS_PUBLIC)
        eq_(extension.latest_version, new_pending_version)
        eq_(extension.latest_public_version, new_public_version)
        extension.reload()
        eq_(extension.status, STATUS_PUBLIC)
        eq_(extension.latest_version, new_pending_version)
        eq_(extension.latest_public_version, new_public_version)

    def test_extension_public_version_deleted(self):
        extension = Extension.objects.create()
        new_public_version = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PUBLIC, version='0.1')
        eq_(extension.status, STATUS_PUBLIC)
        eq_(extension.latest_version, new_public_version)
        eq_(extension.latest_public_version, new_public_version)
        new_public_version.delete()
        with self.assertRaises(ExtensionVersion.DoesNotExist):
            extension.latest_version
        with self.assertRaises(ExtensionVersion.DoesNotExist):
            extension.latest_public_version
        eq_(extension.status, STATUS_NULL)
        eq_(extension.reload().status, STATUS_NULL)

    def test_extension_public_version_deleted_fallback_to_other(self):
        extension = Extension.objects.create()
        ExtensionVersion.objects.create(
            extension=extension, status=STATUS_NULL, version='0.0')
        first_public_version = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PUBLIC, version='0.1')
        second_public_version = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PUBLIC, version='0.2')
        new_pending_version = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PENDING, version='0.3')
        eq_(extension.status, STATUS_PUBLIC)
        eq_(extension.latest_version, new_pending_version)
        eq_(extension.latest_public_version, second_public_version)
        second_public_version.delete()
        eq_(extension.status, STATUS_PUBLIC)
        eq_(extension.latest_version, new_pending_version)
        eq_(extension.latest_public_version, first_public_version)
        extension.reload()
        eq_(extension.status, STATUS_PUBLIC)
        eq_(extension.latest_version, new_pending_version)
        eq_(extension.latest_public_version, first_public_version)

    def test_extension_public_pending_version_deleted_no_change(self):
        extension = Extension.objects.create()
        ExtensionVersion.objects.create(
            extension=extension, status=STATUS_NULL, version='0.1')
        new_public_version = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PUBLIC, version='0.2')
        new_pending_version = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PENDING, version='0.3')
        eq_(extension.status, STATUS_PUBLIC)
        eq_(extension.latest_version, new_pending_version)
        eq_(extension.latest_public_version, new_public_version)
        new_pending_version.delete()
        eq_(extension.status, STATUS_PUBLIC)
        eq_(extension.latest_version, new_public_version)
        eq_(extension.latest_public_version, new_public_version)
        extension.reload()
        eq_(extension.status, STATUS_PUBLIC)
        eq_(extension.latest_version, new_public_version)
        eq_(extension.latest_public_version, new_public_version)

    def test_update_fields_from_manifest_when_version_is_made_public(self):
        new_manifest = {
            'name': u'New Nâme',
            'description': u'New Descriptîon',
            'version': '0.1',
        }
        extension = Extension.objects.create(
            name=u'Old Nâme', description=u'Old Descriptîon')
        version = ExtensionVersion.objects.create(
            extension=extension, manifest=new_manifest, status=STATUS_PENDING,
            version='0.1')
        version.update(status=STATUS_PUBLIC)
        eq_(extension.description, new_manifest['description'])
        eq_(extension.name, new_manifest['name'])

    def test_update_fields_from_manifest_when_public_version_is_deleted(self):
        old_manifest = {
            'name': u'Old Nâme',
            'description': u'Old Descriptîon',
            'version': '0.1',
        }
        new_manifest = {
            'name': u'Deleted Nâme',
            'description': u'Deleted Descriptîon',
            'version': '0.2',
        }
        extension = Extension.objects.create(
            name=u'Deleted Nâme', description=u'Deleted Descriptîon')
        ExtensionVersion.objects.create(
            extension=extension, manifest=old_manifest, status=STATUS_PUBLIC,
            version='0.1')
        version = ExtensionVersion.objects.create(
            extension=extension, manifest=new_manifest, status=STATUS_PUBLIC,
            version='0.2')
        eq_(extension.description, new_manifest['description'])
        eq_(extension.name, new_manifest['name'])
        version.delete()
        eq_(extension.description, old_manifest['description'])
        eq_(extension.name, old_manifest['name'])

    def test_dont_update_fields_from_manifest_when_not_necessary(self):
        new_manifest = {
            'name': u'New Nâme',
            'description': u'New Descriptîon',
            'version': '0.1',
        }
        extension = Extension.objects.create(
            name=u'Old Nâme', description=u'Old Descriptîon')
        ExtensionVersion.objects.create(
            extension=extension, manifest=new_manifest, status=STATUS_PENDING,
            version='0.1')
        extension.reload()
        eq_(extension.description, u'Old Descriptîon')
        eq_(extension.name, u'Old Nâme')


class TestExtensionVersionMethodsAndProperties(TestCase):
    @override_settings(SITE_URL='https://marketpace.example.com/')
    def test_download_url(self):
        extension = Extension(pk=40, uuid='abcdef78123456781234567812345678')
        version = ExtensionVersion(
            pk=4815162342, extension=extension, version='0.40.0')
        eq_(version.download_url,
            'https://marketpace.example.com/downloads/extension/'
            'abcdef78123456781234567812345678/4815162342/extension-0.40.0.zip')

    @override_settings(SITE_URL='https://marketpace.example.com/')
    def test_unsigned_download_url(self):
        extension = Extension(pk=41, uuid='abcdef78123456781234567812345678')
        version = ExtensionVersion(
            pk=2432615184, extension=extension, version='0.41.0')
        eq_(version.unsigned_download_url,
            'https://marketpace.example.com/downloads/extension/unsigned/'
            'abcdef78123456781234567812345678/2432615184/extension-0.41.0.zip')

    def test_file_paths(self):
        extension = Extension(pk=42)
        version = ExtensionVersion(extension=extension, version='0.42.0')
        eq_(version.filename, 'extension-0.42.0.zip')
        eq_(version.file_path,
            os.path.join(settings.EXTENSIONS_PATH, str(extension.pk),
                         version.filename))
        eq_(version.signed_file_path,
            os.path.join(settings.SIGNED_EXTENSIONS_PATH,
                         str(extension.pk), version.filename))

    @override_settings(SITE_URL='https://marketpace.example.com/')
    def test_mini_manifest_url(self):
        extension = Extension(pk=43, uuid='12345678123456781234567812abcdef')
        eq_(extension.mini_manifest_url,
            'https://marketpace.example.com/extension/'
            '12345678123456781234567812abcdef/manifest.json')

    def test_mini_manifest_no_version(self):
        extension = Extension()
        eq_(extension.mini_manifest, {})

    def test_mini_manifest_no_public_version(self):
        manifest = {
            'author': 'Me',
            'description': 'Blah',
            'manifest_version': 2,
            'name': u'Ëxtension',
            'version': '0.44',
        }
        extension = Extension(pk=44, uuid='abcdefabcdefabcdefabcdefabcdef44')
        ExtensionVersion(
            pk=1234, extension=extension, manifest=manifest, version='0.44.0')
        eq_(extension.mini_manifest, {})

    def test_mini_manifest(self):
        manifest = {
            'author': 'Me',
            'description': 'Blah',
            'manifest_version': 2,
            'name': u'Ëxtension',
            'version': '0.45',
        }
        extension = Extension.objects.create(
            status=STATUS_PUBLIC, uuid='abcdefabcdefabcdefabcdefabcdef45')
        ExtensionVersion.objects.create(
            extension=extension, manifest={},
            status=STATUS_PENDING, version='0.44.0')
        version = ExtensionVersion.objects.create(
            extension=extension, manifest=manifest,
            status=STATUS_PUBLIC, size=421, version='0.45.0')
        expected_mini_manifest = {
            'description': 'Blah',
            'developer': {
                'name': 'Me'
            },
            'name': u'Ëxtension',
            'package_path': version.download_url,
            'size': 421,
            'version': '0.45',
        }
        eq_(extension.mini_manifest, expected_mini_manifest)

    @mock.patch('mkt.extensions.models.sign_app')
    @mock.patch('mkt.extensions.models.private_storage')
    @mock.patch('mkt.extensions.models.public_storage')
    @mock.patch.object(ExtensionVersion, 'remove_signed_file')
    def test_sign_and_move_file(self, remove_signed_file_mock,
                                public_storage_mock, private_storage_mock,
                                sign_app_mock):
        extension = Extension(uuid='ab345678123456781234567812345678')
        version = ExtensionVersion(extension=extension, pk=123)
        public_storage_mock.size.return_value = 665
        size = version.sign_and_move_file()
        eq_(size, 665)
        expected_args = (
            private_storage_mock.open.return_value,
            version.signed_file_path,
            json.dumps({
                'id': 'ab345678123456781234567812345678',
                'version': 123,
            })
        )
        eq_(sign_app_mock.call_args[0], expected_args)
        eq_(remove_signed_file_mock.call_count, 0)

    @mock.patch('mkt.extensions.models.sign_app')
    @mock.patch('mkt.extensions.models.private_storage')
    def test_sign_and_move_file_no_uuid(self, private_storage_mock,
                                        sign_app_mock):
        extension = Extension(uuid='')
        version = ExtensionVersion(extension=extension)
        with self.assertRaises(SigningError):
            version.sign_and_move_file()

    @mock.patch('mkt.extensions.models.sign_app')
    @mock.patch('mkt.extensions.models.private_storage')
    def test_sign_and_move_file_no_version_pk(self, private_storage_mock,
                                              sign_app_mock):
        extension = Extension(uuid='12345678123456781234567812345678')
        version = ExtensionVersion(extension=extension)
        with self.assertRaises(SigningError):
            version.sign_and_move_file()

    @mock.patch('mkt.extensions.models.sign_app')
    @mock.patch('mkt.extensions.models.private_storage')
    @mock.patch.object(ExtensionVersion, 'remove_signed_file')
    def test_sign_and_move_file_error(self, remove_signed_file_mock,
                                      private_storage_mock, sign_app_mock):
        extension = Extension(uuid='12345678123456781234567812345678')
        version = ExtensionVersion(extension=extension, pk=123)
        sign_app_mock.side_effect = SigningError
        with self.assertRaises(SigningError):
            version.sign_and_move_file()
        eq_(remove_signed_file_mock.call_count, 1)

    @mock.patch('mkt.extensions.models.private_storage')
    @mock.patch('mkt.extensions.models.public_storage')
    def test_remove_signed_file(self, mocked_public_storage,
                                mocked_private_storage):
        extension = Extension(pk=42, slug='mocked_ext')
        version = ExtensionVersion(extension=extension, pk=123)
        mocked_public_storage.exists.return_value = True
        mocked_private_storage.size.return_value = 668
        size = version.remove_signed_file()
        eq_(size, 668)
        eq_(mocked_public_storage.exists.call_args[0][0],
            version.signed_file_path)
        eq_(mocked_public_storage.delete.call_args[0][0],
            version.signed_file_path)

    @mock.patch('mkt.extensions.models.private_storage')
    @mock.patch('mkt.extensions.models.public_storage')
    def test_remove_signed_file_not_exists(self, public_storage_mock,
                                           mocked_private_storage):
        extension = Extension(pk=42, slug='mocked_ext')
        version = ExtensionVersion(extension=extension, pk=123)
        public_storage_mock.exists.return_value = False
        mocked_private_storage.size.return_value = 669
        size = version.remove_signed_file()
        eq_(size, 669)
        eq_(public_storage_mock.exists.call_args[0][0],
            version.signed_file_path)
        eq_(public_storage_mock.delete.call_count, 0)

    @mock.patch.object(ExtensionVersion, 'sign_and_move_file')
    def test_publish(self, mocked_sign_and_move_file):
        mocked_sign_and_move_file.return_value = 666
        extension = Extension.objects.create(slug='mocked_ext')
        version = ExtensionVersion.objects.create(
            extension=extension, size=0, status=STATUS_PENDING)
        eq_(version.status, STATUS_PENDING)
        eq_(extension.status, STATUS_PENDING)  # Set automatically.
        version.publish()
        eq_(mocked_sign_and_move_file.call_count, 1)
        eq_(version.size, 666)
        eq_(version.status, STATUS_PUBLIC)
        eq_(extension.status, STATUS_PUBLIC)

        # Also reload to make sure the changes hit the database.
        version.reload()
        eq_(version.status, STATUS_PUBLIC)
        eq_(version.size, 666)
        eq_(extension.reload().status, STATUS_PUBLIC)

    @mock.patch.object(ExtensionVersion, 'remove_signed_file')
    def test_reject(self, mocked_remove_signed_file):
        mocked_remove_signed_file.return_value = 667
        extension = Extension.objects.create(slug='mocked_ext')
        version = ExtensionVersion.objects.create(
            extension=extension, size=42, status=STATUS_PENDING)
        eq_(version.status, STATUS_PENDING)
        eq_(extension.status, STATUS_PENDING)  # Set automatically.
        version.reject()
        eq_(mocked_remove_signed_file.call_count, 1)
        eq_(version.size, 667)
        eq_(version.status, STATUS_REJECTED)
        # At the moment Extension are not rejected, merely set back to
        # incomplete since they no longer have a pending or public version.
        eq_(extension.status, STATUS_NULL)

        # Also reload to make sure the changes hit the database.
        version.reload()
        eq_(version.size, 667)
        eq_(version.status, STATUS_REJECTED)
        eq_(extension.reload().status, STATUS_NULL)


class TestExtensionManager(TestCase):
    def test_public(self):
        extension1 = Extension.objects.create(status=STATUS_PUBLIC)
        extension2 = Extension.objects.create(status=STATUS_PUBLIC)
        Extension.objects.create(status=STATUS_NULL)
        eq_(list(Extension.objects.public()), [extension1, extension2])

    def test_pending(self):
        extension1 = Extension.objects.create()
        ExtensionVersion.objects.create(
            extension=extension1, status=STATUS_PENDING, version='1.1')
        extension2 = Extension.objects.create()
        ExtensionVersion.objects.create(
            extension=extension2, status=STATUS_PENDING, version='2.1')
        ExtensionVersion.objects.create(
            extension=extension2, status=STATUS_PUBLIC, version='2.2')
        Extension.objects.create(status=STATUS_PUBLIC)
        Extension.objects.create(status=STATUS_NULL)

        eq_(list(Extension.objects.pending()), [extension1, extension2])


class TestExtensionVersionManager(TestCase):
    def test_public(self):
        extension = Extension.objects.create(status=STATUS_PUBLIC)
        version1 = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PUBLIC, version='1.0')
        version2 = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PUBLIC, version='1.1')
        ExtensionVersion.objects.create(
            extension=extension, status=STATUS_REJECTED, version='1.2')
        ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PENDING, version='1.3')
        eq_(list(ExtensionVersion.objects.public()), [version1, version2])
        eq_(list(extension.versions.public()), [version1, version2])

    def test_pending(self):
        extension = Extension.objects.create()
        ExtensionVersion.objects.create(
            extension=extension, status=STATUS_REJECTED, version='2.0')
        version1 = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PENDING, version='2.1')
        version2 = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PENDING, version='2.2')
        ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PUBLIC, version='2.3')

        eq_(list(ExtensionVersion.objects.pending()), [version1, version2])
