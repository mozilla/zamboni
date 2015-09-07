# -*- coding: utf-8 -*-
import json
import os.path

from django.conf import settings
from django.core.urlresolvers import reverse
from django.db import models, IntegrityError, transaction
from django.dispatch import receiver
from django.forms import ValidationError

import commonware.log
from django_extensions.db.fields.json import JSONField
from django_statsd.clients import statsd
from tower import ugettext as _
from uuidfield.fields import UUIDField

from lib.crypto.packaged import sign_app, SigningError
from mkt.constants.base import (STATUS_CHOICES, STATUS_NULL, STATUS_PENDING,
                                STATUS_PUBLIC, STATUS_REJECTED)
from mkt.extensions.indexers import ExtensionIndexer
from mkt.extensions.utils import ExtensionParser
from mkt.files.models import cleanup_file, nfd_str
from mkt.translations.fields import save_signal, TranslatedField
from mkt.site.helpers import absolutify
from mkt.site.models import ManagerBase, ModelBase
from mkt.site.storage_utils import (copy_stored_file, private_storage,
                                    public_storage)
from mkt.site.utils import cached_property, smart_path
from mkt.webapps.models import clean_slug


log = commonware.log.getLogger('z.extensions')


class ExtensionManager(ManagerBase):
    def pending(self):
        return self.filter(versions__status=STATUS_PENDING).order_by('id')

    def public(self):
        return self.filter(status=STATUS_PUBLIC).order_by('id')


class Extension(ModelBase):
    # Automatically handled fields.
    uuid = UUIDField(auto=True)
    status = models.PositiveSmallIntegerField(
        choices=STATUS_CHOICES.items(), db_index=True, default=STATUS_NULL)

    # Fields for which the manifest is the source of truth - can't be
    # overridden by the API.
    default_language = models.CharField(default=settings.LANGUAGE_CODE,
                                        max_length=10)
    description = TranslatedField(default=None)
    name = TranslatedField(default=None)

    # Fields that can be modified using the API.
    authors = models.ManyToManyField('users.UserProfile')
    slug = models.CharField(max_length=35, unique=True)

    objects = ExtensionManager()

    @cached_property(writable=True)
    def latest_public_version(self):
        return self.versions.filter(status=STATUS_PUBLIC).latest('pk')

    @cached_property(writable=True)
    def latest_version(self):
        return self.versions.latest('pk')

    def clean_slug(self):
        return clean_slug(self, slug_field='slug')

    @classmethod
    def from_upload(cls, upload, user=None):
        """Handle creating/editing the Extension instance and saving it to db,
        as well as file operations, from a FileUpload instance. Can throw
        a ValidationError or SigningError, so should always be called within a
        try/except."""
        parsed_data = ExtensionParser(upload).parse()
        accepted_fields = ('default_language', 'description', 'name')
        data = {k: parsed_data[k] for k in accepted_fields if k in parsed_data}

        # Build a new instance.
        instance = cls.objects.create(**data)

        # Now that the instance has been saved, we can add the author and start
        # saving version data. If everything checks out, a status will be set
        # on the ExtensionVersion we're creating which will automatically be
        # replicated on the Extension instance.
        instance.authors.add(user)
        ExtensionVersion.from_upload(
            upload, parent=instance, parsed_data=parsed_data)
        return instance

    @classmethod
    def get_fallback(cls):
        # Class method needed by the translations app.
        return cls._meta.get_field('default_language')

    @classmethod
    def get_indexer(self):
        return ExtensionIndexer

    def is_public(self):
        return self.status == STATUS_PUBLIC

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
        # name, description and author. To be on the safe side we also copy
        # version. We don't bother with locales at the moment, this probably
        # breaks extensions using https://developer.chrome.com/extensions/i18n
        # but we'll deal with that later.
        try:
            version = self.latest_public_version
        except ExtensionVersion.DoesNotExist:
            return {}
        mini_manifest = {
            'name': version.manifest['name'],
            'package_path': version.download_url,
            'version': version.manifest['version']
        }
        if 'author' in version.manifest:
            mini_manifest['developer'] = {
                'name': version.manifest['author']
            }
        if 'description' in version.manifest:
            mini_manifest['description'] = version.manifest['description']
        return mini_manifest

    @property
    def mini_manifest_url(self):
        return absolutify(reverse('extension.mini_manifest',
                                  kwargs={'uuid': self.uuid}))

    def save(self, *args, **kwargs):
        if not self.slug:
            self.clean_slug()
        return super(Extension, self).save(*args, **kwargs)

    def __unicode__(self):
        return u'%s: %s' % (self.pk, self.name)

    def update_status_according_to_versions(self):
        """Update `status`, `latest_version` and `latest_public_version`
        properties depending on the `status` on the ExtensionVersion
        instances attached to this Extension."""
        # If there is a public version available, the extension should be
        # public. If not, and if there is a pending version available, it
        # should be pending. Otherwise it should just be incomplete.
        if self.versions.filter(status=STATUS_PUBLIC).exists():
            self.update(status=STATUS_PUBLIC)
        elif self.versions.filter(status=STATUS_PENDING).exists():
            self.update(status=STATUS_PENDING)
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
    extension = models.ForeignKey(Extension, related_name='versions')

    default_language = models.CharField(default=settings.LANGUAGE_CODE,
                                        max_length=10)
    manifest = JSONField()
    version = models.CharField(max_length=23, default='')
    status = models.PositiveSmallIntegerField(
        choices=STATUS_CHOICES.items(), db_index=True, default=STATUS_NULL)

    class Meta:
        unique_together = (('extension', 'version'),)

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
        prefix = os.path.join(
            settings.ADDONS_PATH, 'extensions', str(self.extension.pk))
        return os.path.join(prefix, nfd_str(self.filename))

    @classmethod
    def get_fallback(cls):
        # Class method needed by the translations app.
        return cls._meta.get_field('default_language')

    @classmethod
    def from_upload(cls, upload, parent=None, parsed_data=None):
        """Handle creating/editing the ExtensionVersion instance and saving it
        to db, as well as file operations, from a FileUpload instance.

        `parent` parameter must be passed so that we can attach the instance to
        an Extension. `data` can be passed to avoid parsing the `upload` twice
        if that was already done.

        Can throw a ValidationError or SigningError, so should always be called
        within a try/except."""
        # FIXME: do we keep Extension name&description as non-editable ? If so,
        # when uploading a new version, it should update them on the Extension
        # instance.
        if parent is None:
            raise ValueError('ExtensionVersion.from_upload() needs a parent.')

        if parsed_data is None:
            parsed_data = ExtensionParser(upload).parse()
        accepted_fields = ('default_language', 'manifest', 'version')
        data = {k: parsed_data[k] for k in accepted_fields if k in parsed_data}
        data['extension'] = parent

        # Build a new instance.
        try:
            with transaction.atomic():
                instance = cls.objects.create(**data)
        except IntegrityError:
            raise ValidationError(
                _('An extension with this version number already exists.'))

        # Now that the instance has been saved, we can generate a file path,
        # move the file and set it to PENDING. That should also set the status
        # on the parent.
        instance.handle_file_operations(upload)
        instance.update(status=STATUS_PENDING)
        return instance

    def handle_file_operations(self, upload):
        """Copy the file attached to a FileUpload to the Extension instance."""
        upload.path = smart_path(nfd_str(upload.path))

        if private_storage.exists(self.file_path):
            # The filename should not exist. If it does, it means we are trying
            # to re-upload the same version. This should have been caught
            # before, so just raise an exception.
            raise RuntimeError(
                'Trying to upload a file to a destination that already exists')

        # Copy file from fileupload. This uses private_storage for now as the
        # unreviewed, unsigned filename is private.
        copy_stored_file(
            upload.path, self.file_path,
            src_storage=private_storage, dst_storage=private_storage)

    def publish(self):
        """Publish this extension version to public."""
        self.sign_and_move_file()
        self.update(status=STATUS_PUBLIC)

    def reject(self):
        """Reject this extension version."""
        self.update(status=STATUS_REJECTED)
        self.remove_signed_file()

    def remove_signed_file(self):
        if public_storage.exists(self.signed_file_path):
            public_storage.delete(self.signed_file_path)

    def sign_and_move_file(self):
        """Sign and move extension file from the unsigned path (`file_path`) on
        private storage to the signed path (`signed_file_path`) on public
        storage."""
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
                self.remove_signed_file()  # Clean up.
                raise

    @property
    def signed_file_path(self):
        prefix = os.path.join(settings.ADDONS_PATH, 'extensions-signed',
                              str(self.extension.pk))
        return os.path.join(prefix, nfd_str(self.filename))

    def __unicode__(self):
        return u'%s' % (self.pk,)

    @property
    def unsigned_download_url(self):
        kwargs = {
            'filename': self.filename,
            'uuid': self.extension.uuid,
            'version_id': self.pk,
        }
        return absolutify(
            reverse('extension.download_unsigned', kwargs=kwargs))


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


# Update status on Extension when an ExtensionVersion changes.
@receiver([models.signals.post_delete, models.signals.post_save],
          sender=ExtensionVersion, dispatch_uid='extension_version_change')
def update_extension_status(sender, instance, **kw):
    # FIXME: should render obsolete older pending uploads as well.
    instance.extension.update_status_according_to_versions()


# Save translations before saving Extensions instances with translated fields.
models.signals.pre_save.connect(save_signal, sender=Extension,
                                dispatch_uid='extension_translations')
models.signals.pre_save.connect(save_signal, sender=ExtensionVersion,
                                dispatch_uid='extension_version_translations')

# Delete files when deleting ExtensionVersion instances.
models.signals.post_delete.connect(cleanup_file, sender=ExtensionVersion,
                                   dispatch_uid='extension_cleanup_file')
