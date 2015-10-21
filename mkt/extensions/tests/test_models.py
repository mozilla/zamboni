# -*- coding: utf-8 -*-
import json
import mock
import os.path
from datetime import datetime

from django.conf import settings
from django.db import IntegrityError
from django.test.utils import override_settings

from nose.tools import eq_, ok_
from rest_framework.exceptions import ParseError

from lib.crypto.packaged import SigningError
from mkt.constants.applications import DEVICE_GAIA
from mkt.constants.base import (STATUS_NULL, STATUS_OBSOLETE, STATUS_PENDING,
                                STATUS_PUBLIC, STATUS_REJECTED)
from mkt.constants.regions import RESTOFWORLD, USA
from mkt.extensions.models import Extension, ExtensionVersion
from mkt.files.tests.test_models import UploadCreationMixin, UploadTest
from mkt.site.storage_utils import private_storage, public_storage
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
        'author': u'Mozillâ',
        'name': u'My Lîttle Extension'
    }

    def setUp(self):
        super(TestExtensionUpload, self).setUp()
        self.user = UserProfile.objects.get(pk=2519)

    def tearDown(self):
        super(TestExtensionUpload, self).tearDown()
        # Explicitly delete the Extensions to clean up leftover files. By
        # using the queryset method we're bypassing the custom delete() method,
        # but still sending pre_delete and post_delete signals.
        Extension.objects.all().delete()

    def test_auto_create_slug(self):
        extension = Extension.objects.create()
        eq_(extension.slug, 'extension')
        extension = Extension.objects.create()
        eq_(extension.slug, 'extension-1')
        extension = Extension.objects.create(name=u'Mŷ Ëxtension')
        eq_(extension.slug, u'mŷ-ëxtension')
        # Slug clashes are avoided automatically:
        extension = Extension.objects.create(
            name=u'Mŷ Ëxtension', slug=u'mŷ-ëxtension')
        eq_(extension.slug, u'mŷ-ëxtension-1')

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
        eq_(extension.author, u'Mozillâ')
        eq_(extension.name, u'My Lîttle Extension')
        eq_(extension.default_language, 'en-GB')
        eq_(extension.description, u'A Dummÿ Extension')
        eq_(extension.name.locale, 'en-gb')
        eq_(extension.description.locale, 'en-gb')
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
        eq_(old_version.status, STATUS_OBSOLETE)
        eq_(older_version.status, STATUS_OBSOLETE)

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

    def test_upload_new_version_existing_version_integrity_error(self):
        # Like test_upload_new_version_existing_version(), but this time the
        # version number does not clash when we do the check, it clashes later
        # when we do the db insert (race condition).
        extension = Extension.objects.create()
        upload = self.upload('extension')
        with mock.patch.object(
                ExtensionVersion.objects, 'create') as create_mock:
            create_mock.side_effect = IntegrityError
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

    def test_handle_file_upload_operations_path_already_exists(self):
        upload = self.upload('extension')
        extension = Extension()
        version = ExtensionVersion(extension=extension)
        with mock.patch(
                'mkt.extensions.models.private_storage') as storage_mock:
            storage_mock.exists.return_value = True
            with self.assertRaises(RuntimeError):
                version.handle_file_upload_operations(upload)


class TestExtensionAndExtensionVersionDeletion(TestCase):
    def tearDown(self):
        super(TestExtensionAndExtensionVersionDeletion, self).tearDown()
        # Explicitly delete the Extensions to clean up leftover files. By
        # using the queryset method we're bypassing the custom delete() method,
        # but still sending pre_delete and post_delete signals.
        Extension.objects.all().delete()

    def _create_files_for_version(self, version):
        """Create dummy files for a version."""
        file_path = version.file_path
        with private_storage.open(file_path, 'w') as f:
            f.write('sample data\n')
        signed_file_path = version.signed_file_path
        with public_storage.open(signed_file_path, 'w') as f:
            f.write('sample signed data\n')
        assert private_storage.exists(file_path)
        assert public_storage.exists(signed_file_path)
        return file_path, signed_file_path

    def test_hard_delete_with_file(self):
        """Test that when a Extension instance is hard-deleted, the
        ExtensionVersion referencing it are also hard-deleted, as well as the
        attached files."""
        extension = Extension.objects.create()
        version = ExtensionVersion.objects.create(
            extension=extension, version='0.1')
        file_path, signed_file_path = self._create_files_for_version(version)
        extension.delete(hard_delete=True)
        assert not Extension.objects.count()
        assert not ExtensionVersion.objects.count()
        assert not private_storage.exists(file_path)
        assert not public_storage.exists(signed_file_path)

    def test_hard_delete_version_with_file(self):
        """Test that when a ExtensionVersion instance is hard-deleted, the
        attached files are too."""
        extension = Extension.objects.create()
        version = ExtensionVersion.objects.create(
            extension=extension, version='0.1')
        file_path, signed_file_path = self._create_files_for_version(version)
        version.delete(hard_delete=True)
        assert Extension.objects.count()  # Parent Extension was not deleted.
        assert not ExtensionVersion.objects.count()
        assert not private_storage.exists(file_path)
        assert not public_storage.exists(signed_file_path)

    def test_hard_delete_no_file(self):
        """Test that the Extension instance can be hard-deleted."""
        extension = Extension.objects.create()
        ExtensionVersion.objects.create(extension=extension, version='0.1')
        extension.delete(hard_delete=True)
        assert not ExtensionVersion.objects.count()
        assert not Extension.objects.count()

    def test_hard_delete_version_no_file(self):
        """Test that the ExtensionVersion instance can be hard-deleted without
        the files being present."""
        extension = Extension.objects.create()
        version = ExtensionVersion.objects.create(
            extension=extension, version='0.1')
        version.delete(hard_delete=True)
        assert not ExtensionVersion.objects.count()
        assert Extension.objects.count()  # Parent Extension was not deleted.

    def test_soft_delete(self):
        """Test that when a Extension instance is soft-deleted, the slug
        and the deleted properties change."""
        extension = Extension.objects.create()
        ExtensionVersion.objects.create(extension=extension, version='0.1')
        extension.delete()
        eq_(extension.slug, None)
        eq_(extension.deleted, True)
        # Even after reload:
        extension.reload()
        eq_(extension.slug, None)
        eq_(extension.deleted, True)

    def test_soft_delete_version(self):
        """Test that when a ExtensionVersion instance is soft-deleted, the
        version and the deleted properties change."""
        extension = Extension.objects.create()
        version = ExtensionVersion.objects.create(
            extension=extension, version='0.1')
        version.delete()
        eq_(version.version, None)
        eq_(version.deleted, True)
        # Even after reload:
        version.reload()
        eq_(version.version, None)
        eq_(version.deleted, True)

    def test_soft_delete_with_file(self):
        """Test that when a Extension instance is soft-deleted, nothing is
        truly deleted, and versions are not affected."""
        extension = Extension.objects.create()
        version = ExtensionVersion.objects.create(
            extension=extension, version='0.1')
        file_path = version.file_path
        signed_file_path = version.signed_file_path
        assert not private_storage.exists(file_path)
        assert not public_storage.exists(signed_file_path)
        extension.delete()
        extension.reload()
        eq_(extension.deleted, True)
        # ExtensionVersion is still present, but hidden when using
        # without_deleted().
        assert ExtensionVersion.objects.count()
        assert not Extension.objects.without_deleted().count()
        assert Extension.objects.count()

    def test_soft_delete_version_with_file(self):
        """Test that when a ExtensionVersion instance is soft-deleted, nothing
        is truly deleted."""
        extension = Extension.objects.create()
        version = ExtensionVersion.objects.create(
            extension=extension, version='0.1')
        file_path, signed_file_path = self._create_files_for_version(version)
        version.delete()
        version.reload()
        eq_(version.deleted, True)
        # Parent Extension was not deleted.
        assert Extension.objects.without_deleted().count()
        # ExtensionVersion is still present, but hidden when using
        # without_deleted().
        assert not ExtensionVersion.objects.without_deleted().count()
        assert ExtensionVersion.objects.count()
        # Files were not deleted.
        assert private_storage.exists(file_path)
        assert public_storage.exists(signed_file_path)

    def test_hard_delete_empty_version(self):
        """Test that the ExtensionVersion instance can be hard-deleted with the
        version field being empty."""
        extension = Extension.objects.create()
        version = ExtensionVersion.objects.create(extension=extension)
        version.delete(hard_delete=True)
        assert not ExtensionVersion.objects.count()

    @mock.patch.object(Extension, 'update_status_according_to_versions')
    def test_status_update_on_hard_deletion(self, update_status_mock):
        """Test that when an ExtensionVersion is hard-deleted, we call
        update_status_according_to_versions() on the Extension."""
        extension = Extension.objects.create()
        version = ExtensionVersion.objects.create(extension=extension)
        update_status_mock.reset_mock()
        eq_(update_status_mock.call_count, 0)
        version.delete(hard_delete=True)
        eq_(update_status_mock.call_count, 1)

    @mock.patch.object(Extension, 'update_status_according_to_versions')
    def test_status_update_on_soft_deletion(self, update_status_mock):
        """Test that when an ExtensionVersion is soft-deleted, we call
        update_status_according_to_versions() on the Extension."""
        extension = Extension.objects.create()
        version = ExtensionVersion.objects.create(extension=extension)
        update_status_mock.reset_mock()
        eq_(update_status_mock.call_count, 0)
        version.delete()
        eq_(version.deleted, True)
        eq_(update_status_mock.call_count, 1)

    def test_undelete(self):
        extension = Extension.objects.create(deleted=True, slug=None)
        extension.undelete()
        ok_(extension.slug)
        eq_(extension.deleted, False)
        eq_(Extension.objects.without_deleted().count(), 1)

    def test_version_undelete(self):
        manifest = {
            'version': u'0.1',
        }
        extension = Extension.objects.create()
        version = ExtensionVersion.objects.create(
            deleted=True, extension=extension, manifest=manifest, version=None)
        version.undelete()
        eq_(version.deleted, False)
        eq_(version.version, u'0.1')
        eq_(ExtensionVersion.objects.without_deleted().count(), 1)

    def test_undelete_not_deleted(self):
        extension = Extension()
        eq_(extension.undelete(), False)

    def test_undelete_version_not_deleted(self):
        version = ExtensionVersion()
        eq_(version.undelete(), False)


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

    @mock.patch('mkt.search.indexers.BaseIndexer.unindex')
    def test_delete_search_index_single(self, unindex_mock):
        extension = Extension.objects.create()
        extension.delete(hard_delete=True)
        eq_(unindex_mock.call_count, 1)


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

    def test_extension_pending_version_hard_deleted(self):
        extension = Extension.objects.create()
        new_version = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PENDING, version='0.1')
        eq_(extension.status, STATUS_PENDING)
        eq_(extension.latest_version, new_version)
        new_version.delete(hard_delete=True)
        eq_(extension.status, STATUS_NULL)
        with self.assertRaises(ExtensionVersion.DoesNotExist):
            extension.latest_version

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

    def test_pending_version_hard_deleted_fallback_to_other(self):
        extension = Extension.objects.create()
        old_version = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PENDING, version='0.1')
        new_version = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PENDING, version='0.2')
        eq_(extension.status, STATUS_PENDING)
        eq_(extension.latest_version, new_version)
        new_version.delete(hard_delete=True)
        eq_(extension.status, STATUS_PENDING)
        eq_(extension.latest_version, old_version)
        extension.reload()
        eq_(extension.status, STATUS_PENDING)
        eq_(extension.latest_version, old_version)

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

    def test_public_extension_pending_version_hard_deleted_no_change(self):
        extension = Extension.objects.create()
        old_version = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PENDING, version='0.1')
        new_version = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PENDING, version='0.2')
        eq_(extension.status, STATUS_PENDING)
        eq_(extension.latest_version, new_version)
        new_version.delete(hard_delete=True)
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

    def test_extension_public_version_hard_deleted(self):
        extension = Extension.objects.create()
        new_public_version = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PUBLIC, version='0.1')
        eq_(extension.status, STATUS_PUBLIC)
        eq_(extension.latest_version, new_public_version)
        eq_(extension.latest_public_version, new_public_version)
        new_public_version.delete(hard_delete=True)
        with self.assertRaises(ExtensionVersion.DoesNotExist):
            extension.latest_version
        with self.assertRaises(ExtensionVersion.DoesNotExist):
            extension.latest_public_version
        eq_(extension.status, STATUS_NULL)
        eq_(extension.reload().status, STATUS_NULL)

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
        second_public_version.delete(hard_delete=True)
        eq_(extension.status, STATUS_PUBLIC)
        eq_(extension.latest_version, new_pending_version)
        eq_(extension.latest_public_version, first_public_version)
        extension.reload()
        eq_(extension.status, STATUS_PUBLIC)
        eq_(extension.latest_version, new_pending_version)
        eq_(extension.latest_public_version, first_public_version)

    def test_extension_public_version_hard_deleted_fallback_to_other(self):
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
        new_pending_version.delete(hard_delete=True)
        eq_(extension.status, STATUS_PUBLIC)
        eq_(extension.latest_version, new_public_version)
        eq_(extension.latest_public_version, new_public_version)
        extension.reload()
        eq_(extension.status, STATUS_PUBLIC)
        eq_(extension.latest_version, new_public_version)
        eq_(extension.latest_public_version, new_public_version)

    def test_extension_public_pending_version_hard_deleted_no_change(self):
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

    def test_new_version_rejected(self):
        extension = Extension.objects.create()
        eq_(extension.status, STATUS_NULL)
        version = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_REJECTED, version='0.1')
        eq_(extension.status, STATUS_REJECTED)
        eq_(extension.latest_version, version)

        new_version = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_REJECTED, version='0.2')
        extension.reload()
        eq_(extension.status, STATUS_REJECTED)
        eq_(extension.latest_version, new_version)

    def test_update_fields_from_manifest_when_version_is_made_public(self):
        new_manifest = {
            'author': u' New Authôr',
            'name': u'\n New Nâme ',
            'description': u'New Descriptîon \t ',
            'version': '0.1',
        }
        extension = Extension.objects.create(
            author=u'Old Âuthor', description=u'Old Descriptîon',
            name=u'Old Nâme')
        version = ExtensionVersion.objects.create(
            extension=extension, manifest=new_manifest, status=STATUS_PENDING,
            version='0.1')
        version.update(status=STATUS_PUBLIC)
        # Leading and trailing whitespace are stripped.
        eq_(extension.author, u'New Authôr')
        eq_(extension.description, u'New Descriptîon')
        eq_(extension.name, u'New Nâme')
        # Locale should be en-US since none is specified in the manifest.
        eq_(extension.name.locale, 'en-us')
        eq_(extension.description.locale, 'en-us')

    def test_update_manifest_when_public_version_is_hard_deleted(self):
        old_manifest = {
            'author': u'Old Authôr',
            'description': u'Old Descriptîon',
            'name': u'Old Nâme',
            'version': '0.1',
        }
        new_manifest = {
            'author': u'Deleted Authôr',
            'description': u'Deleted Descriptîon',
            'name': u'Deleted Nâme',
            'version': '0.2',
        }
        extension = Extension.objects.create()
        ExtensionVersion.objects.create(
            extension=extension, manifest=old_manifest, status=STATUS_PUBLIC,
            version='0.1')
        version = ExtensionVersion.objects.create(
            extension=extension, manifest=new_manifest, status=STATUS_PUBLIC,
            version='0.2')
        eq_(extension.author, new_manifest['author'])
        eq_(extension.description, new_manifest['description'])
        eq_(extension.name, new_manifest['name'])
        version.delete(hard_delete=True)
        eq_(extension.author, old_manifest['author'])
        eq_(extension.description, old_manifest['description'])
        eq_(extension.name, old_manifest['name'])

    def test_update_manifest_when_public_version_is_deleted(self):
        old_manifest = {
            'author': u'Old Authôr',
            'description': u'Old Descriptîon',
            'name': u'Old Nâme',
            'version': '0.1',
        }
        new_manifest = {
            'author': u'Deleted Authôr',
            'description': u'Deleted Descriptîon',
            'name': u'Deleted Nâme',
            'version': '0.2',
        }
        extension = Extension.objects.create()
        ExtensionVersion.objects.create(
            extension=extension, manifest=old_manifest, status=STATUS_PUBLIC,
            version='0.1')
        version = ExtensionVersion.objects.create(
            extension=extension, manifest=new_manifest, status=STATUS_PUBLIC,
            version='0.2')
        eq_(extension.author, new_manifest['author'])
        eq_(extension.description, new_manifest['description'])
        eq_(extension.name, new_manifest['name'])
        version.delete()
        eq_(extension.author, old_manifest['author'])
        eq_(extension.description, old_manifest['description'])
        eq_(extension.name, old_manifest['name'])

    def test_dont_update_fields_from_manifest_when_not_necessary(self):
        new_manifest = {
            'author': u' New Authôr',
            'name': u'\n New Nâme ',
            'description': u'New Descriptîon \t ',
            'version': '0.1',
        }
        extension = Extension.objects.create(
            author=u'Old Authôr', description=u'Old Descriptîon',
            name=u'Old Nâme')
        ExtensionVersion.objects.create(
            extension=extension, manifest=new_manifest, status=STATUS_PENDING,
            version='0.1')
        extension.reload()
        eq_(extension.author, u'Old Authôr')
        eq_(extension.description, u'Old Descriptîon')
        eq_(extension.name, u'Old Nâme')


class TestExtensionAndExtensionVersionMethodsAndProperties(TestCase):
    def test_unicode(self):
        extension = Extension(pk=42, name=u'lolé', slug=u'lolé')
        version = ExtensionVersion(pk=42, extension=extension, version=u'0.42')
        ok_(unicode(extension))
        ok_(unicode(version))

    def test_get_fallback(self):
        eq_(Extension.get_fallback(),
            Extension._meta.get_field('default_language'))
        eq_(ExtensionVersion.get_fallback(),
            ExtensionVersion._meta.get_field('default_language'))

    def test_is_dummy_content_for_qa(self):
        # This method is only here for compatbility with apps, not used at the
        # moment.
        extension = Extension()
        eq_(extension.is_dummy_content_for_qa(), False)

    def test_latest_public_version_does_not_include_deleted(self):
        """Test that deleted ExtensionVersion are not taken into account when
        determining the latest public version."""
        extension = Extension.objects.create()
        ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PUBLIC)
        version = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PUBLIC)
        ExtensionVersion.objects.create(
            extension=extension, status=STATUS_REJECTED)
        ExtensionVersion.objects.create(
            extension=extension, status=STATUS_OBSOLETE)
        ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PENDING)
        ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PUBLIC, deleted=True)
        eq_(extension.latest_public_version, version)

    def test_latest_version_does_not_include_deleted(self):
        """Test that deleted ExtensionVersion are not taken into account when
        determining the latest version."""
        extension = Extension.objects.create()
        ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PUBLIC)
        ExtensionVersion.objects.create(
            extension=extension, status=STATUS_REJECTED)
        ExtensionVersion.objects.create(
            extension=extension, status=STATUS_OBSOLETE)
        version = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PENDING)
        ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PUBLIC, deleted=True)
        eq_(extension.latest_version, version)

    def test_devices(self):
        eq_(Extension().devices, [DEVICE_GAIA.id])

    def test_devices_names(self):
        eq_(Extension().device_names, ['firefoxos'])

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

    @override_settings(SITE_URL='https://marketpace.example.com/')
    def test_reviewer_download_url(self):
        extension = Extension(pk=42, uuid='abcdef78123456781234567812345678')
        version = ExtensionVersion(
            pk=4815162342, extension=extension, version='0.42.0')
        eq_(version.reviewer_download_url,
            'https://marketpace.example.com/downloads/extension/reviewers/'
            'abcdef78123456781234567812345678/4815162342/extension-0.42.0.zip')

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
        eq_(version.reviewer_signed_file_path,
            os.path.join(settings.EXTENSIONS_PATH,
                         str(extension.pk), 'reviewers', version.filename))

    def test_is_public(self):
        extension = Extension(disabled=False, status=STATUS_PUBLIC)
        eq_(extension.is_public(), True)

        for status in (STATUS_NULL, STATUS_PENDING):
            extension.status = status
            eq_(extension.is_public(), False)

    def test_is_public_disabled(self):
        extension = Extension(disabled=True)
        for status in (STATUS_NULL, STATUS_PENDING, STATUS_PUBLIC):
            extension.status = status
            eq_(extension.is_public(), False)

    @override_settings(SITE_URL='https://marketpace.example.com/')
    def test_mini_manifest_url(self):
        extension = Extension(pk=43, uuid='12345678123456781234567812abcdef')
        eq_(extension.mini_manifest_url,
            'https://marketpace.example.com/extension/'
            '12345678123456781234567812abcdef/manifest.json')

    def test_mini_manifest_no_version(self):
        extension = Extension(pk=42)
        eq_(extension.mini_manifest, {})

    def test_mini_manifest_no_public_version(self):
        manifest = {
            'you_should_not_see': 'this_manifest'
        }
        extension = Extension.objects.create(
            uuid='abcdefabcdefabcdefabcdefabcdef44')
        ExtensionVersion.objects.create(
            extension=extension, manifest=manifest, status=STATUS_PENDING,
            version='0.44.0')
        eq_(extension.mini_manifest, {})

    def test_mini_manifest(self):
        manifest = {
            'author': 'Me',
            'description': 'Blah',
            'manifest_version': 2,
            'name': u'Ëxtension',
            'version': '0.45.0',
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
            'id': 'abcdefabcdefabcdefabcdefabcdef45',
            'name': u'Ëxtension',
            'package_path': version.download_url,
            'size': 421,
            'version': '0.45.0',
        }
        eq_(extension.mini_manifest, expected_mini_manifest)

    @override_settings(SITE_URL='https://marketpace.example.com/')
    def test_reviewer_mini_manifest_url(self):
        extension = Extension(pk=43, uuid='12345678123456781234567812abcdef')
        version = ExtensionVersion(extension=extension, pk=4343)
        eq_(version.reviewer_mini_manifest_url,
            'https://marketpace.example.com/extension/reviewers/'
            '12345678123456781234567812abcdef/4343/manifest.json')

    def test_reviewer_mini_manifest(self):
        manifest = {
            'author': 'Me',
            'description': 'Blah',
            'manifest_version': 2,
            'name': u'Ëxtension',
            'version': '0.55.0',
        }
        extension = Extension.objects.create(
            status=STATUS_PENDING, uuid='abcdefabcdefabcdefabcdefabcdef45')
        version = ExtensionVersion.objects.create(
            extension=extension, manifest=manifest,
            status=STATUS_PENDING, version='0.54.0')
        expected_mini_manifest = {
            'description': 'Blah',
            'developer': {
                'name': 'Me'
            },
            'id': 'reviewer-abcdefabcdefabcdefabcdefabcdef45-%d' % version.pk,
            'name': u'Ëxtension',
            'package_path': version.reviewer_download_url,
            'version': '0.55.0',
        }
        eq_(version.reviewer_mini_manifest, expected_mini_manifest)

    @mock.patch('mkt.extensions.models.sign_app')
    @mock.patch('mkt.extensions.models.private_storage')
    @mock.patch('mkt.extensions.models.public_storage')
    @mock.patch.object(ExtensionVersion, 'remove_public_signed_file')
    def test_sign_file(self, remove_public_signed_file_mock,
                       public_storage_mock, private_storage_mock,
                       sign_app_mock):
        extension = Extension(uuid='ab345678123456781234567812345678')
        version = ExtensionVersion(extension=extension, pk=123)
        public_storage_mock.size.return_value = 665
        size = version.sign_file()
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
        eq_(remove_public_signed_file_mock.call_count, 0)

    @mock.patch('mkt.extensions.models.sign_app')
    @mock.patch('mkt.extensions.models.private_storage')
    def test_sign_file_no_uuid(self, private_storage_mock,
                               sign_app_mock):
        extension = Extension(uuid='')
        version = ExtensionVersion(extension=extension)
        with self.assertRaises(SigningError):
            version.sign_file()

    @mock.patch('mkt.extensions.models.sign_app')
    @mock.patch('mkt.extensions.models.private_storage')
    def test_sign_file_no_version_pk(self, private_storage_mock,
                                     sign_app_mock):
        extension = Extension(uuid='12345678123456781234567812345678')
        version = ExtensionVersion(extension=extension)
        with self.assertRaises(SigningError):
            version.sign_file()

    @mock.patch('mkt.extensions.models.sign_app')
    @mock.patch('mkt.extensions.models.private_storage')
    @mock.patch.object(ExtensionVersion, 'remove_public_signed_file')
    def test_sign_file_error(self, remove_public_signed_file_mock,
                             private_storage_mock, sign_app_mock):
        extension = Extension(uuid='12345678123456781234567812345678')
        version = ExtensionVersion(extension=extension, pk=123)
        sign_app_mock.side_effect = SigningError
        with self.assertRaises(SigningError):
            version.sign_file()
        eq_(remove_public_signed_file_mock.call_count, 1)

    @mock.patch('mkt.extensions.models.private_storage')
    @mock.patch('mkt.extensions.models.ExtensionVersion.reviewer_sign_file')
    def test_reviewer_sign_if_necessary(self, reviewer_sign_file_mock,
                                        mocked_private_storage):
        mocked_private_storage.exists.return_value = False
        extension = Extension(pk=40)
        version = ExtensionVersion(extension=extension, pk=404040)

        version.reviewer_sign_if_necessary()
        eq_(reviewer_sign_file_mock.call_count, 1)

    @mock.patch('mkt.extensions.models.private_storage')
    @mock.patch('mkt.extensions.models.ExtensionVersion.reviewer_sign_file')
    def test_reviewer_sign_if_necessary_exists(self, reviewer_sign_file_mock,
                                               mocked_private_storage):
        mocked_private_storage.exists.return_value = True
        extension = Extension(pk=40)
        version = ExtensionVersion(extension=extension, pk=404040)

        version.reviewer_sign_if_necessary()
        eq_(reviewer_sign_file_mock.call_count, 0)

    @mock.patch('mkt.extensions.models.sign_app')
    @mock.patch('mkt.extensions.models.private_storage')
    @mock.patch('mkt.extensions.models.public_storage')
    def test_reviewer_sign_file(self, public_storage_mock,
                                private_storage_mock, sign_app_mock):
        extension = Extension(uuid='ab345678123456781234567812345678')
        version = ExtensionVersion(extension=extension, pk=123)
        version.reviewer_sign_file()
        expected_args = (
            private_storage_mock.open.return_value,
            version.reviewer_signed_file_path,
            json.dumps({
                'id': 'reviewer-ab345678123456781234567812345678-123',
                'version': 123,
            }),
        )
        expected_kwargs = {'reviewer': True}
        eq_(sign_app_mock.call_args[0], expected_args)
        eq_(sign_app_mock.call_args[1], expected_kwargs)
        eq_(private_storage_mock.delete.call_count, 0)

    @mock.patch('mkt.extensions.models.sign_app')
    @mock.patch('mkt.extensions.models.private_storage')
    def test_reviewer_sign_file_no_uuid(self, private_storage_mock,
                                        sign_app_mock):
        extension = Extension(uuid='')
        version = ExtensionVersion(extension=extension)
        with self.assertRaises(SigningError):
            version.reviewer_sign_file()

    @mock.patch('mkt.extensions.models.sign_app')
    @mock.patch('mkt.extensions.models.private_storage')
    def test_reviewer_sign_file_no_version_pk(self, private_storage_mock,
                                              sign_app_mock):
        extension = Extension(uuid='12345678123456781234567812345678')
        version = ExtensionVersion(extension=extension)
        with self.assertRaises(SigningError):
            version.reviewer_sign_file()

    @mock.patch('mkt.extensions.models.sign_app')
    @mock.patch('mkt.extensions.models.private_storage')
    def test_reviewer_sign_file_error(self, private_storage_mock,
                                      sign_app_mock):
        extension = Extension(uuid='12345678123456781234567812345678')
        version = ExtensionVersion(extension=extension, pk=123)
        sign_app_mock.side_effect = SigningError
        with self.assertRaises(SigningError):
            version.reviewer_sign_file()
        eq_(private_storage_mock.delete.call_count, 1)

    @mock.patch('mkt.extensions.models.private_storage')
    @mock.patch('mkt.extensions.models.public_storage')
    def test_remove_public_signed_file(self, mocked_public_storage,
                                       mocked_private_storage):
        extension = Extension(pk=42, slug='mocked_ext')
        version = ExtensionVersion(extension=extension, pk=123)
        mocked_public_storage.exists.return_value = True
        mocked_private_storage.size.return_value = 668
        size = version.remove_public_signed_file()
        eq_(size, 668)
        eq_(mocked_public_storage.exists.call_args[0][0],
            version.signed_file_path)
        eq_(mocked_public_storage.delete.call_args[0][0],
            version.signed_file_path)

    @mock.patch('mkt.extensions.models.private_storage')
    @mock.patch('mkt.extensions.models.public_storage')
    def test_remove_public_signed_file_not_exists(self, public_storage_mock,
                                                  mocked_private_storage):
        extension = Extension(pk=42, slug='mocked_ext')
        version = ExtensionVersion(extension=extension, pk=123)
        public_storage_mock.exists.return_value = False
        mocked_private_storage.size.return_value = 669
        size = version.remove_public_signed_file()
        eq_(size, 669)
        eq_(public_storage_mock.exists.call_args[0][0],
            version.signed_file_path)
        eq_(public_storage_mock.delete.call_count, 0)

    @mock.patch.object(ExtensionVersion, 'sign_file')
    @mock.patch('mkt.extensions.models.datetime')
    def test_publish(self, datetime_mock, mocked_sign_file):
        datetime_mock.utcnow.return_value = (
            # Microseconds are not saved by MySQL, so set it to 0 to make sure
            # our comparisons still work once the model is saved to the db.
            datetime.utcnow().replace(microsecond=0))
        mocked_sign_file.return_value = 666
        extension = Extension.objects.create(slug='mocked_ext')
        version = ExtensionVersion.objects.create(
            extension=extension, size=0, status=STATUS_PENDING)
        eq_(version.status, STATUS_PENDING)
        eq_(extension.status, STATUS_PENDING)  # Set automatically.
        version.publish()
        eq_(mocked_sign_file.call_count, 1)
        eq_(version.size, 666)
        eq_(version.status, STATUS_PUBLIC)
        eq_(extension.status, STATUS_PUBLIC)

        # Also reload to make sure the changes hit the database.
        extension.reload()
        version.reload()
        eq_(version.status, STATUS_PUBLIC)
        eq_(version.size, 666)
        eq_(extension.last_updated, datetime_mock.utcnow.return_value)
        eq_(extension.status, STATUS_PUBLIC)

    @mock.patch.object(ExtensionVersion, 'remove_public_signed_file')
    def test_reject(self, remove_public_signed_file_mock):
        remove_public_signed_file_mock.return_value = 667
        extension = Extension.objects.create(slug='mocked_ext')
        version = ExtensionVersion.objects.create(
            extension=extension, size=42, status=STATUS_PENDING)
        eq_(version.status, STATUS_PENDING)
        eq_(extension.status, STATUS_PENDING)  # Set automatically.
        version.reject()
        eq_(remove_public_signed_file_mock.call_count, 1)
        eq_(version.size, 667)
        eq_(version.status, STATUS_REJECTED)
        eq_(extension.status, STATUS_REJECTED)

        # Also reload to make sure the changes hit the database.
        version.reload()
        eq_(version.size, 667)
        eq_(version.status, STATUS_REJECTED)
        eq_(extension.reload().status, STATUS_REJECTED)


class TestExtensionPopularity(TestCase):
    def test_unique(self):
        extension = Extension.objects.create()
        extension2 = Extension.objects.create()

        extension.popularity.create(region=RESTOFWORLD.id)
        extension.popularity.create(region=USA.id)

        extension2.popularity.create(region=RESTOFWORLD.id)
        with self.assertRaises(IntegrityError):
            extension.popularity.create(region=RESTOFWORLD.id)


class TestExtensionQuerySetAndManager(TestCase):
    def test_by_identifier(self):
        # Force a high-pk deliberately, to make sure we don't just test with
        # single-digit pks.
        extension = Extension.objects.create(slug='lol', pk=9999)
        Extension.objects.create(slug='not-lol')
        eq_(Extension.objects.by_identifier(extension.pk), extension)
        eq_(Extension.objects.by_identifier(unicode(extension.pk)), extension)
        eq_(Extension.objects.by_identifier(extension.slug), extension)
        # Should still work even with deleted, as long as we are not combining
        # with without_deleted() method.
        Extension.objects.all().update(deleted=True)
        eq_(Extension.objects.by_identifier(extension.pk), extension)
        eq_(Extension.objects.by_identifier(extension.slug), extension)

    def test_by_identifier_without_deleted(self):
        # Note: deleted Extensions are not supposed to have slugs anymore, so
        # this test might seem a bit useless, but it's here to prove that
        # chaining without_deleted() with by_identifier() works fine, since it
        # was not trivial to make it work.

        # Force a high-pk deliberately, to make sure we don't just test with
        # single-digit pks.
        extension = Extension.objects.create(slug='lol', pk=9999)
        Extension.objects.create(slug='not-lol')
        eq_(Extension.objects.without_deleted().by_identifier(extension.pk),
            extension)
        eq_(Extension.objects.without_deleted().by_identifier(
            unicode(extension.pk)), extension)
        eq_(Extension.objects.without_deleted().by_identifier(extension.slug),
            extension)
        Extension.objects.all().update(deleted=True)
        with self.assertRaises(Extension.DoesNotExist):
            Extension.objects.without_deleted().by_identifier(extension.pk)
        with self.assertRaises(Extension.DoesNotExist):
            Extension.objects.without_deleted().by_identifier(extension.slug)

    def test_extensive_method_chaining(self):
        extension = Extension.objects.create(name=u'lôl', status=STATUS_PUBLIC)
        result = Extension.objects.without_deleted().public().transform(
            lambda o: o).by_identifier(extension.pk)
        eq_(result.pk, extension.pk)
        eq_(result.name, u'lôl')

    def test_public(self):
        extension1 = Extension.objects.create(status=STATUS_PUBLIC)
        extension2 = Extension.objects.create(
            deleted=True, status=STATUS_PUBLIC)
        Extension.objects.create(status=STATUS_NULL)
        Extension.objects.create(status=STATUS_PUBLIC, disabled=True)
        eq_(list(Extension.objects.public()), [extension2, extension1])
        eq_(list(Extension.objects.without_deleted().public()), [extension1])

    def test_pending_with_versions(self):
        extension1 = Extension.objects.create()
        ExtensionVersion.objects.create(
            extension=extension1, status=STATUS_PENDING, version='1.1')
        extension2 = Extension.objects.create(deleted=True)
        ExtensionVersion.objects.create(
            extension=extension2, status=STATUS_PENDING, version='2.1')
        ExtensionVersion.objects.create(
            extension=extension2, status=STATUS_PUBLIC, version='2.2')
        extension3 = Extension.objects.create()
        ExtensionVersion.objects.create(
            extension=extension3, deleted=True, status=STATUS_PENDING,
            version='3.1')
        Extension.objects.create(status=STATUS_PUBLIC)
        Extension.objects.create(status=STATUS_NULL)
        disabled_extension = Extension.objects.create(disabled=True)
        ExtensionVersion.objects.create(
            extension=disabled_extension, status=STATUS_PENDING, version='3.1')

        eq_(list(Extension.objects.pending_with_versions()),
            [extension2, extension1])
        eq_(list(Extension.objects.without_deleted().pending_with_versions()),
            [extension1])

    def test_pending(self):
        extension1 = Extension.objects.create(status=STATUS_PENDING)

        extension2 = Extension.objects.create()
        ExtensionVersion.objects.create(
            extension=extension2, status=STATUS_PENDING, version='2.1')
        extension2.update(status=STATUS_PUBLIC)

        self.assertSetEqual(list(Extension.objects.pending()), [extension1])


class TestExtensionVersionQuerySetAndManager(TestCase):
    def test_public(self):
        extension = Extension.objects.create(status=STATUS_PUBLIC)
        version1 = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PUBLIC, version='1.0')
        version2 = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PUBLIC, version='1.1',
            deleted=True)
        ExtensionVersion.objects.create(
            extension=extension, status=STATUS_REJECTED, version='1.2')
        ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PENDING, version='1.3')
        eq_(list(ExtensionVersion.objects.public()), [version1, version2])
        eq_(list(extension.versions.public()), [version1, version2])

        eq_(list(ExtensionVersion.objects.without_deleted().public()),
            [version1])
        eq_(list(extension.versions.without_deleted().public()), [version1])

    def test_pending(self):
        extension = Extension.objects.create()
        ExtensionVersion.objects.create(
            extension=extension, status=STATUS_REJECTED, version='2.0')
        version1 = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PENDING, version='2.1')
        version2 = ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PENDING, version='2.2',
            deleted=True)
        ExtensionVersion.objects.create(
            extension=extension, status=STATUS_PUBLIC, version='2.3')

        eq_(list(ExtensionVersion.objects.pending()), [version1, version2])
        eq_(list(extension.versions.pending()), [version1, version2])

        eq_(list(ExtensionVersion.objects.without_deleted().pending()),
            [version1])
        eq_(list(extension.versions.without_deleted().pending()), [version1])
