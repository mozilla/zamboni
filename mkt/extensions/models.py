# -*- coding: utf-8 -*-
import json
import os.path
from datetime import datetime

from django.conf import settings
from django.core.urlresolvers import reverse
from django.db import models, IntegrityError, transaction
from django.dispatch import receiver

import commonware.log
from django_extensions.db.fields.json import JSONField
from django_statsd.clients import statsd
from rest_framework.exceptions import ParseError
from tower import ugettext as _
from uuidfield.fields import UUIDField

from lib.crypto.packaged import sign_app, SigningError
from lib.utils import static_url
from mkt.constants.applications import DEVICE_GAIA, DEVICE_TYPES
from mkt.constants.base import (STATUS_CHOICES, STATUS_FILE_CHOICES,
                                STATUS_NULL, STATUS_OBSOLETE, STATUS_PENDING,
                                STATUS_PUBLIC, STATUS_REJECTED)
from mkt.extensions.indexers import ExtensionIndexer
from mkt.extensions.tasks import fetch_icon
from mkt.extensions.validation import ExtensionValidator
from mkt.files.models import cleanup_file, nfd_str
from mkt.translations.fields import save_signal, TranslatedField
from mkt.site.helpers import absolutify
from mkt.site.models import ManagerBase, ModelBase
from mkt.site.storage_utils import (copy_stored_file, private_storage,
                                    public_storage)
from mkt.site.utils import cached_property, get_icon_url, smart_path
from mkt.translations.utils import to_language
from mkt.webapps.models import clean_slug


log = commonware.log.getLogger('z.extensions')


class ExtensionQuerySet(models.QuerySet):
    def by_identifier(self, identifier):
        """Return a single Extension from an identifier, slug or pk."""
        # Slugs can't contain only digits.
        if unicode(identifier).isdigit():
            return self.get(pk=int(identifier))
        else:
            return self.get(slug=identifier)

    def pending(self):
        return self.filter(disabled=False, status=STATUS_PENDING)

    def pending_with_versions(self):
        return self.filter(disabled=False, versions__deleted=False,
                           versions__status=STATUS_PENDING)

    def public(self):
        return self.filter(disabled=False, status=STATUS_PUBLIC)

    def without_deleted(self):
        return self.filter(deleted=False)


class ExtensionVersionQuerySet(models.QuerySet):
    def pending(self):
        return self.filter(status=STATUS_PENDING)

    def public(self):
        return self.filter(status=STATUS_PUBLIC)

    def rejected(self):
        return self.filter(status=STATUS_REJECTED)

    def without_deleted(self):
        return self.filter(deleted=False)


class Extension(ModelBase):
    # Automatically handled fields.
    deleted = models.BooleanField(default=False, editable=False)
    icon_hash = models.CharField(max_length=8, blank=True)
    last_updated = models.DateTimeField(blank=True, null=True, editable=False)
    status = models.PositiveSmallIntegerField(
        choices=STATUS_CHOICES.items(), default=STATUS_NULL, editable=False)
    uuid = UUIDField(auto=True, editable=False)

    # Fields for which the manifest is the source of truth - can't be
    # overridden by the API.
    author = models.CharField(default='', editable=False, max_length=128)
    default_language = models.CharField(default=settings.LANGUAGE_CODE,
                                        editable=False, max_length=10)
    description = TranslatedField(default=None, editable=False)
    name = TranslatedField(default=None, editable=False)

    # Fields that can be modified using the API.
    authors = models.ManyToManyField('users.UserProfile')
    disabled = models.BooleanField(default=False)
    slug = models.CharField(max_length=35, null=True, unique=True)

    objects = ManagerBase.from_queryset(ExtensionQuerySet)()

    manifest_is_source_of_truth_fields = (
        'author', 'description', 'default_language', 'name')

    class Meta:
        ordering = ('-id', )
        index_together = (('deleted', 'disabled', 'status'),)

    @cached_property(writable=True)
    def latest_public_version(self):
        return self.versions.without_deleted().public().latest('pk')

    @cached_property(writable=True)
    def latest_version(self):
        return self.versions.without_deleted().latest('pk')

    def clean_slug(self):
        return clean_slug(self, slug_field='slug')

    def delete(self, *args, **kwargs):
        """Delete this instance.

        By default, a soft-delete is performed, only hiding the instance from
        the custom manager methods without actually removing it from the
        database. pre_delete and post_delete signals are *not* sent in that
        case. The slug will be set to None during the process.

        Can be overridden by passing `hard_delete=True` keyword argument, in
        which case it behaves like a regular delete() call instead."""
        hard_delete = kwargs.pop('hard_delete', False)
        if hard_delete:
            # Real, hard delete.
            return super(Extension, self).delete(*args, **kwargs)
        # Soft delete.
        # Since we have a unique constraint with slug, set it to None when
        # deleting. Undelete should re-generate it - it might differ from the
        # original slug, but that's why you should be careful when deleting...
        self.update(deleted=True, slug=None)

    @property
    def devices(self):
        """Device ids the Extension is compatible with.

        For now, hardcoded to only return Firefox OS."""
        return [DEVICE_GAIA.id]

    @property
    def device_names(self):
        """Device names the Extension is compatible with.

        Used by the API."""
        return [DEVICE_TYPES[device_id].api_name for device_id in self.devices]

    @classmethod
    def extract_and_validate_upload(cls, upload):
        """Validate and extract manifest from a FileUpload instance.

        Can raise ParseError."""
        with private_storage.open(upload.path) as file_obj:
            # The file will already have been uploaded at this point, so force
            # the content type to make the ExtensionValidator happy. We just
            # need to validate the contents.
            file_obj.content_type = 'application/zip'
            manifest_contents = ExtensionValidator(file_obj).validate()
        return manifest_contents

    @classmethod
    def extract_manifest_fields(cls, manifest_data, fields=None):
        """Extract the specified `fields` from `manifest_data`, applying
        transformations if necessary. If `fields` is absent, then use
        `cls.manifest_is_source_of_truth_fields`."""
        if fields is None:
            fields = cls.manifest_is_source_of_truth_fields
        data = {k: manifest_data[k] for k in fields if k in manifest_data}

        # Determine default language to use for translations.
        # Web Extensions Manifest contains locales (e.g. "en_US"), not
        # languages (e.g. "en-US"). The field is also called differently as a
        # result (default_locale vs default_language), so we need to transform
        # both the key and the value before adding it to data. A default value
        # needs to be set to correctly generate the translated fields below.
        default_language = to_language(manifest_data.get(
            'default_locale', cls._meta.get_field('default_language').default))
        if 'default_language' in fields:
            data['default_language'] = default_language

        # Be nice and strip leading / trailing whitespace chars from
        # strings.
        for key, value in data.items():
            if isinstance(value, basestring):
                data[key] = value.strip()

        # Translated fields should not be extracted as simple strings,
        # otherwise we end up setting a locale on the translation that is
        # dependent on the locale of the thread. Use dicts instead, always
        # setting default_language as the language for now (since we don't
        # support i18n in web extensions yet).
        for field in cls._meta.translated_fields:
            field_name = field.name
            if field_name in data:
                data[field_name] = {
                    default_language: manifest_data[field_name]
                }

        return data

    @classmethod
    def from_upload(cls, upload, user=None):
        """Handle creating/editing the Extension instance and saving it to db,
        as well as file operations, from a FileUpload instance. Can throw
        a ParseError or SigningError, so should always be called within a
        try/except."""
        manifest_contents = cls.extract_and_validate_upload(upload)
        data = cls.extract_manifest_fields(manifest_contents)

        # Build a new instance.
        instance = cls.objects.create(**data)

        # Now that the instance has been saved, we can add the author and start
        # saving version data. If everything checks out, a status will be set
        # on the ExtensionVersion we're creating which will automatically be
        # replicated on the Extension instance.
        instance.authors.add(user)
        version = ExtensionVersion.from_upload(
            upload, parent=instance, manifest_contents=manifest_contents)

        # Trigger icon fetch task asynchronously if necessary now that we have
        # an extension and a version.
        if 'icons' in manifest_contents:
            fetch_icon.delay(instance.pk, version.pk)
        return instance

    @classmethod
    def get_fallback(cls):
        """Class method returning the field holding the default language to use
        in translations for this instance.

        *Needs* to be called get_fallback() and *needs* to be a classmethod,
        that's what the translations app requires."""
        return cls._meta.get_field('default_language')

    def get_icon_dir(self):
        return os.path.join(settings.EXTENSION_ICONS_PATH, str(self.pk / 1000))

    def get_icon_url(self, size):
        return get_icon_url(static_url('EXTENSION_ICON_URL'), self, size)

    @classmethod
    def get_indexer(cls):
        return ExtensionIndexer

    @property
    def icon_type(self):
        return 'png' if self.icon_hash else ''

    def is_dummy_content_for_qa(self):
        """
        Returns whether this extension is a dummy extension used for testing
        only or not.

        Used by mkt.search.utils.extract_popularity_trending_boost() - the
        method needs to exist, but we are not using it yet.
        """
        return False

    def is_public(self):
        return (not self.deleted and not self.disabled and
                self.status == STATUS_PUBLIC)

    @property
    def mini_manifest(self):
        """Mini-manifest used for install/update on FxOS devices, in dict form.

        It follows the Mozilla App Manifest format (because that's what FxOS
        requires to install/update add-ons), *not* the Web Extension manifest
        format.
        """
        # Platform "translates" back the mini-manifest into an app manifest and
        # verifies that some specific key properties in the real manifest match
        # what's found in the mini-manifest. To prevent manifest mismatch
        # errors, we need to copy those properties from the real manifest:
        # name, description and author. To help Firefox OS display useful info
        # to the user we also copy content_scripts and version.
        # We don't bother with locales at the moment, this probably breaks
        # extensions using https://developer.chrome.com/extensions/i18n but
        # we'll deal with that later.
        try:
            version = self.latest_public_version
        except ExtensionVersion.DoesNotExist:
            return {}
        manifest = version.manifest
        mini_manifest = {
            # 'id' here is the uuid, like in sign_file(). This is used by
            # platform to do blocklisting.
            'id': self.uuid,
            'name': manifest['name'],
            'package_path': version.download_url,
            'size': version.size,
            'version': manifest['version']
        }
        if 'author' in manifest:
            # author is copied as a different key to match app manifest format.
            mini_manifest['developer'] = {
                'name': manifest['author']
            }
        if 'content_scripts' in manifest:
            mini_manifest['content_scripts'] = manifest['content_scripts']
        if 'description' in manifest:
            mini_manifest['description'] = manifest['description']
        return mini_manifest

    @property
    def mini_manifest_url(self):
        return absolutify(reverse('extension.mini_manifest',
                                  kwargs={'uuid': self.uuid}))

    def save(self, *args, **kwargs):
        if not self.deleted:
            # Always clean slug before saving, to avoid clashes.
            self.clean_slug()
        return super(Extension, self).save(*args, **kwargs)

    def __unicode__(self):
        return u'%s: %s' % (self.pk, self.name)

    def undelete(self):
        """Undelete this instance, making it available to all manager methods
        again and restoring its version number.

        Return False if it was not marked as deleted, True otherwise.
        Will re-generate a slug, that might differ from the original one if it
        was taken in the meantime."""
        if not self.deleted:
            return False
        self.clean_slug()
        self.update(deleted=False, slug=self.slug)
        return True

    def update_manifest_fields_from_latest_public_version(self):
        """Update all fields for which the manifest is the source of truth
        with the manifest from the latest public add-on."""
        try:
            version = self.latest_public_version
        except ExtensionVersion.DoesNotExist:
            return
        if not version.manifest:
            return
        # Trigger icon fetch task asynchronously if necessary now that we have
        # an extension and a version.
        if 'icons' in version.manifest:
            fetch_icon.delay(self.pk, version.pk)

        # We need to re-extract the fields from manifest contents because some
        # fields like default_language are transformed before being stored.
        data = self.extract_manifest_fields(version.manifest)
        return self.update(**data)

    def update_status_according_to_versions(self):
        """Update `status`, `latest_version` and `latest_public_version`
        properties depending on the `status` on the ExtensionVersion
        instances attached to this Extension."""
        # If there is a public version available, the extension should be
        # public. If not, and if there is a pending version available, it
        # should be pending. If not, and if there is a rejected version
        # available, it should be rejected. Otherwise it should just be
        # incomplete.
        versions = self.versions.without_deleted()
        if versions.public().exists():
            self.update(status=STATUS_PUBLIC)
        elif versions.pending().exists():
            self.update(status=STATUS_PENDING)
        elif versions.rejected().exists():
            self.update(status=STATUS_REJECTED)
        else:
            self.update(status=STATUS_NULL)
        # Delete latest_version and latest_public_version properties, since
        # they are writable cached_properties they will be reset the next time
        # they are accessed.
        try:
            if self.latest_version:
                del self.latest_version
        except ExtensionVersion.DoesNotExist:
            pass
        try:
            if self.latest_public_version:
                del self.latest_public_version
        except ExtensionVersion.DoesNotExist:
            pass


class ExtensionVersion(ModelBase):
    # None of these fields should be directly editable by developers, they are
    # all set automatically from actions or extracted from the manifest.
    extension = models.ForeignKey(Extension, editable=False,
                                  related_name='versions')
    default_language = models.CharField(default=settings.LANGUAGE_CODE,
                                        editable=False, max_length=10)
    deleted = models.BooleanField(default=False, editable=False)
    manifest = JSONField(editable=False)
    reviewed = models.DateTimeField(editable=False, null=True)
    version = models.CharField(max_length=23, default=None, editable=False,
                               null=True)
    size = models.PositiveIntegerField(default=0, editable=False)  # In bytes.
    status = models.PositiveSmallIntegerField(
        choices=STATUS_FILE_CHOICES.items(), default=STATUS_NULL,
        editable=False)

    objects = ManagerBase.from_queryset(ExtensionVersionQuerySet)()

    class Meta:
        ordering = ('id', )
        index_together = (('extension', 'deleted', 'status'),)
        unique_together = (('extension', 'version'),)

    def delete(self, *args, **kwargs):
        """Delete this instance.

        By default, a soft-delete is performed, only hiding the instance from
        the custom manager methods without actually removing it from the
        database. pre_delete and post_delete signals are *not* sent in that
        case. The version property will be set to None during the process.

        Can be overridden by passing `hard_delete=True` keyword argument, in
        which case it behaves like a regular delete() call instead."""
        hard_delete = kwargs.pop('hard_delete', False)
        if hard_delete:
            # Real, hard delete.
            return super(ExtensionVersion, self).delete(*args, **kwargs)
        # Soft delete.
        # Since we have a unique constraint with version, set it to None when
        # deleting. Undelete should extract it again from the manifest.
        self.update(deleted=True, version=None)

    @property
    def download_url(self):
        kwargs = {
            'filename': self.filename,
            'uuid': self.extension.uuid,
            'version_id': self.pk,
        }
        return absolutify(reverse('extension.download_signed', kwargs=kwargs))

    @property
    def filename(self):
        """Filename to use when storing the file in storage."""
        # The filename needs to be unique for a given version.
        return 'extension-%s.zip' % self.version

    @property
    def file_path(self):
        """Path to the unsigned archive for this version, on
        private storage."""
        prefix = os.path.join(settings.EXTENSIONS_PATH, str(self.extension.pk))
        return os.path.join(prefix, nfd_str(self.filename))

    @classmethod
    def from_upload(cls, upload, parent=None, manifest_contents=None):
        """Handle creating/editing the ExtensionVersion instance and saving it
        to db, as well as file operations, from a FileUpload instance.

        `parent` parameter must be passed so that we can attach the instance to
        an Extension. `manifest_contents` can be passed to avoid parsing twice
        if that was already done by the caller.

        Can throw a ParseError, so should always be called
        within a try/except."""
        if parent is None:
            raise ValueError('ExtensionVersion.from_upload() needs a parent.')

        if manifest_contents is None:
            manifest_contents = Extension.extract_and_validate_upload(upload)

        fields = ('default_language', 'version')
        data = Extension.extract_manifest_fields(manifest_contents, fields)
        data['manifest'] = manifest_contents
        data['extension'] = parent

        # Check if the version number is higher than the latest version.
        try:
            version = parent.latest_version.version
            if not cls.is_version_number_higher(data['version'], version):
                raise ParseError(
                    _(u'Version number must be higher than the latest version '
                      u'uploaded for this Add-on, which is "%s".' % version))
        except cls.DoesNotExist:
            pass

        # Build a new instance.
        try:
            with transaction.atomic():
                instance = cls.objects.create(**data)
        except IntegrityError:
            raise ParseError(
                _(u'An Add-on with this version number already exists.'))

        # Now that the instance has been saved, we can generate a file path
        # and move the file.
        size = instance.handle_file_upload_operations(upload)

        # Now that the file is there, all that's left is making older pending
        # versions obsolete and setting this one as pending. That should also
        # set the status on the parent.
        instance.set_older_pending_versions_as_obsolete()
        instance.update(size=size, status=STATUS_PENDING)
        return instance

    @classmethod
    def get_fallback(cls):
        """Class method returning the field holding the default language to use
        in translations for this instance.

        *Needs* to be called get_fallback() and *needs* to be a classmethod,
        that's what the translations app requires."""
        return cls._meta.get_field('default_language')

    def handle_file_upload_operations(self, upload):
        """Copy the file attached to a FileUpload to the Extension instance.

        Return the file size."""
        upload.path = smart_path(nfd_str(upload.path))

        if private_storage.exists(self.file_path):
            # The filename should not exist. If it does, it means we are trying
            # to re-upload the same version. This should have been caught
            # before, so just raise an exception.
            raise RuntimeError(
                'Trying to upload a file to a destination that already exists:'
                ' %s' % self.file_path)

        # Copy file from fileupload. This uses private_storage for now as the
        # unreviewed, unsigned filename is private.
        copy_stored_file(
            upload.path, self.file_path,
            src_storage=private_storage, dst_storage=private_storage)

        return private_storage.size(self.file_path)

    @classmethod
    def is_version_number_higher(cls, version1, version2):
        """Return True if `version1` is higher than `version2`."""
        v1 = [int(v) for v in version1.split('.')]
        v2 = [int(v) for v in version2.split('.')]
        return v1 > v2

    def publish(self):
        """Publicize this extension version.

        Update last_updated and reviewed fields at the same time."""
        now = datetime.utcnow()
        size = self.sign_file()
        self.extension.update(last_updated=now)
        self.update(size=size, status=STATUS_PUBLIC, reviewed=now)

    def reject(self):
        """Reject this extension version."""
        size = self.remove_public_signed_file()
        self.update(size=size, status=STATUS_REJECTED)

    def remove_public_signed_file(self):
        """Remove the public signed file if it exists.

        Return the size of the unsigned file, to be used by the caller to
        update the size property on the current instance."""
        if public_storage.exists(self.signed_file_path):
            public_storage.delete(self.signed_file_path)
        return private_storage.size(self.file_path)

    @property
    def reviewer_download_url(self):
        kwargs = {
            'filename': self.filename,
            'uuid': self.extension.uuid,
            'version_id': self.pk,
        }
        return absolutify(
            reverse('extension.download_signed_reviewer', kwargs=kwargs))

    @property
    def review_id(self):
        """Unique identifier for this extension+version so that reviewers can
        install different versions of the same non-public add-ons side by side
        for testing, and it won't conflict with the "real" public add-on.

        Used in signing and in the reviewer-specific mini-manifest."""
        return 'reviewer-{guid}-{version_id}'.format(
            guid=self.extension.uuid, version_id=self.pk)

    @property
    def reviewer_mini_manifest(self):
        """Reviewer-specific mini-manifest used for install/update of this
        particular version by reviewers on FxOS devices, in dict form.
        """
        mini_manifest = {
            'id': self.review_id,
            'name': self.manifest['name'],
            'package_path': self.reviewer_download_url,
            # Size is not included, we don't store the reviewer file size,
            # we don't even know if it has been generated yet at this point.
            'version': self.manifest['version']
        }
        if 'author' in self.manifest:
            mini_manifest['developer'] = {
                'name': self.manifest['author']
            }
        if 'content_scripts' in self.manifest:
            mini_manifest['content_scripts'] = self.manifest['content_scripts']
        if 'description' in self.manifest:
            mini_manifest['description'] = self.manifest['description']
        return mini_manifest

    @property
    def reviewer_mini_manifest_url(self):
        return absolutify(reverse('extension.mini_manifest_reviewer', kwargs={
            'uuid': self.extension.uuid, 'version_id': self.pk}))

    def reviewer_sign_file(self):
        """Sign the original file (`file_path`) with reviewer certs, then move
        the signed file to the reviewers-specific signed path
        (`reviewer_signed_file_path`) on private storage."""
        if not self.extension.uuid:
            raise SigningError('Need uuid to be set to sign')
        if not self.pk:
            raise SigningError('Need version pk to be set to sign')
        ids = json.dumps({
            'id': self.review_id,
            'version': self.pk
        })
        with statsd.timer('extensions.sign_reviewer'):
            try:
                # This will read the file from self.file_path, generate a
                # reviewer signature and write the signed file to
                # self.reviewer_signed_file_path.
                sign_app(private_storage.open(self.file_path),
                         self.reviewer_signed_file_path, ids, reviewer=True)
            except SigningError:
                log.info(
                    '[ExtensionVersion:%s] Reviewer Signing failed' % self.pk)
                if private_storage.exists(self.reviewer_signed_file_path):
                    private_storage.delete(self.reviewer_signed_file_path)
                raise

    @property
    def reviewer_signed_file_path(self):
        """Path to the reviewer-specific signed archive for this version,
        on private storage.

        May not exist if the version has not been signed for review yet."""
        prefix = os.path.join(
            settings.EXTENSIONS_PATH, str(self.extension.pk), 'reviewers')
        return os.path.join(prefix, nfd_str(self.filename))

    def reviewer_sign_if_necessary(self):
        """Simple wrapper around reviewer_sign_file() that generates the
        reviewer-specific signed package if necessary."""
        if not private_storage.exists(self.reviewer_signed_file_path):
            self.reviewer_sign_file()

    def set_older_pending_versions_as_obsolete(self):
        """Set all pending versions older than this one attached to the same
        Extension as STATUS_OBSOLETE.

        To be on the safe side this method does not trigger signals and needs
        to be called when creating a new pending version, before actually
        changing its status to PENDING. That way we avoid having extra versions
        laying around when we automatically update the status on the parent
        Extension."""
        qs = self.__class__.objects.without_deleted().pending().filter(
            extension=self.extension, pk__lt=self.pk)

        # Call <queryset>.update() directly, bypassing signals etc, that should
        # not be needed since it should be followed by a self.save().
        qs.update(status=STATUS_OBSOLETE)

    def sign_file(self):
        """Sign the original file (`file_path`), then move signed extension
        file to the signed path (`signed_file_path`) on public storage. The
        original file remains on private storage.

        Return the signed file size."""
        if not self.extension.uuid:
            raise SigningError('Need uuid to be set to sign')
        if not self.pk:
            raise SigningError('Need version pk to be set to sign')

        ids = json.dumps({
            # 'id' needs to be an unique identifier not shared with anything
            # else (other extensions, langpacks, webapps...), but should not
            # change when there is an update.
            'id': self.extension.uuid,
            # 'version' should be an integer and should be monotonically
            # increasing.
            'version': self.pk
        })
        with statsd.timer('extensions.sign'):
            try:
                # This will read the file from self.file_path, generate a
                # signature and write the signed file to self.signed_file_path.
                sign_app(private_storage.open(self.file_path),
                         self.signed_file_path, ids)
            except SigningError:
                log.info('[ExtensionVersion:%s] Signing failed' % self.pk)
                self.remove_public_signed_file()  # Clean up.
                raise
        return public_storage.size(self.signed_file_path)

    @property
    def signed_file_path(self):
        """Path to the signed archive for this version, on public storage.

        May not exist if the version has not been reviewed yet."""
        prefix = os.path.join(settings.SIGNED_EXTENSIONS_PATH,
                              str(self.extension.pk))
        return os.path.join(prefix, nfd_str(self.filename))

    def undelete(self):
        """Undelete this instance, making it available to all manager methods
        again and restoring its version number.

        Return False if it was not marked as deleted, True otherwise.
        May raise IntegrityError if another instance has been uploaded with the
        same version number in the meantime."""
        if not self.deleted:
            return False
        data = Extension.extract_manifest_fields(self.manifest, ('version',))
        self.update(deleted=False, **data)
        return True

    def __unicode__(self):
        return u'%s %s' % (self.extension.slug, self.version)

    @property
    def unsigned_download_url(self):
        kwargs = {
            'filename': self.filename,
            'uuid': self.extension.uuid,
            'version_id': self.pk,
        }
        return absolutify(
            reverse('extension.download_unsigned', kwargs=kwargs))


class ExtensionPopularity(ModelBase):
    extension = models.ForeignKey(Extension, related_name='popularity')
    value = models.FloatField(default=0.0)
    # When region=0, we count across all regions.
    region = models.PositiveIntegerField(null=False, default=0, db_index=True)

    class Meta:
        unique_together = ('extension', 'region')


class WebsiteTrending(ModelBase):
    extension = models.ForeignKey(Extension, related_name='trending')
    value = models.FloatField(default=0.0)
    # When region=0, it's trending using install counts across all regions.
    region = models.PositiveIntegerField(null=False, default=0, db_index=True)

    class Meta:
        unique_together = ('extension', 'region')


# Update ElasticSearch index on save.
@receiver(models.signals.post_save, sender=Extension,
          dispatch_uid='extension_index')
def update_search_index(sender, instance, **kw):
    instance.get_indexer().index_ids([instance.id])


# Remove from ElasticSearch index on delete.
@receiver(models.signals.post_delete, sender=Extension,
          dispatch_uid='extension_unindex')
def delete_search_index(sender, instance, **kw):
    instance.get_indexer().unindex(instance.id)


@receiver([models.signals.post_delete, models.signals.post_save],
          sender=ExtensionVersion, dispatch_uid='extension_version_change')
def update_extension_status_and_manifest_fields(sender, instance, **kw):
    """Update extension status as well as fields for which the manifest is the
    source of truth when an ExtensionVersion is made public or was public and
    is deleted."""
    instance.extension.update_status_according_to_versions()
    if instance.status == STATUS_PUBLIC:
        instance.extension.update_manifest_fields_from_latest_public_version()


# Save translations before saving Extensions instances with translated fields.
models.signals.pre_save.connect(save_signal, sender=Extension,
                                dispatch_uid='extension_translations')
models.signals.pre_save.connect(save_signal, sender=ExtensionVersion,
                                dispatch_uid='extension_version_translations')

# Delete files when deleting ExtensionVersion instances.
models.signals.post_delete.connect(cleanup_file, sender=ExtensionVersion,
                                   dispatch_uid='extension_cleanup_file')
