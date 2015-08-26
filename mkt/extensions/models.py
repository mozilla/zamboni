# -*- coding: utf-8 -*-
import json
import os.path

from django.conf import settings
from django.db import models
from django.dispatch import receiver

import commonware.log
from django_extensions.db.fields.json import JSONField
from django_statsd.clients import statsd
from uuidfield.fields import UUIDField

from lib.crypto.packaged import sign_app, SigningError
from mkt.constants.base import (STATUS_CHOICES, STATUS_NULL, STATUS_PENDING,
                                STATUS_PUBLIC, STATUS_REJECTED)
from mkt.extensions.indexers import ExtensionIndexer
from mkt.extensions.utils import ExtensionParser
from mkt.files.models import cleanup_file, nfd_str
from mkt.translations.fields import save_signal, TranslatedField
from mkt.translations.utils import to_language
from mkt.site.models import ManagerBase, ModelBase
from mkt.site.storage_utils import (copy_stored_file, private_storage,
                                    public_storage)
from mkt.site.utils import smart_path
from mkt.webapps.models import clean_slug


log = commonware.log.getLogger('z.extensions')


class ExtensionManager(ManagerBase):
    def pending(self):
        return self.filter(status=STATUS_PENDING).order_by('id')


class Extension(ModelBase):
    uuid = UUIDField(auto=True)

    # Fields for which the manifest is the source of truth - can't be
    # overridden by the API.
    default_language = models.CharField(default=settings.LANGUAGE_CODE,
                                        max_length=10)
    manifest = JSONField()
    version = models.CharField(max_length=255, default='')

    # Fields that can be modified using the API.
    authors = models.ManyToManyField('users.UserProfile')
    name = TranslatedField(default=None)
    slug = models.CharField(max_length=35, unique=True)
    status = models.PositiveSmallIntegerField(
        choices=STATUS_CHOICES.items(), db_index=True, default=STATUS_NULL)

    objects = ExtensionManager()

    def clean_slug(self):
        return clean_slug(self, slug_field='slug')

    @property
    def download_url(self):
        raise NotImplementedError

    @property
    def filename(self):
        return 'extension-%s.zip' % self.version

    @property
    def file_path(self):
        prefix = os.path.join(settings.ADDONS_PATH, 'extensions', str(self.pk))
        return os.path.join(prefix, nfd_str(self.filename))

    @property
    def file_version(self):
        """Version number used in signing. Must be an integer and should be
        monotonically increasing for each new version. Currently set to 0 since
        we don't support updates yet."""
        return 0

    @classmethod
    def from_upload(cls, upload, user=None, instance=None):
        """Handle creating/editing the Extension instance and saving it to db,
        as well as file operations, from a FileUpload instance. Can throw
        a ValidationError or SigningError, so should always be called within a
        try/except."""
        if instance is not None:
            # Not implemented yet. Need to deal with versions correctly, we
            # don't know yet if we want to keep older versions around or not,
            # how status changes etc.
            raise NotImplementedError

        parser = ExtensionParser(upload, instance=instance)
        data = parser.parse()
        fields = ('version', 'name', 'default_language')
        default_locale = data.get('default_locale')

        if default_locale:
            # We actually need language (en-US) for translations, not locale
            # (en_US). The extension contains locales though, so transform the
            # field in the manifest before storing in db.
            data['default_language'] = to_language(default_locale)

        # Filter out parsing results to only keep fields we store in db.
        data = dict((k, v) for k, v in data.items() if k in fields)

        # Build a new instance.
        instance = cls(**data)
        instance.manifest = parser.manifest_contents
        instance.save()

        # Now that the instance has been saved, we can add the author,
        # generate a file path, move the file and set it to PENDING.
        instance.authors.add(user)
        instance.handle_file_operations(upload)
        instance.update(status=STATUS_PENDING)
        return instance

    @classmethod
    def get_fallback(cls):
        # Class method needed by the translations app.
        return cls._meta.get_field('default_language')

    @classmethod
    def get_indexer(self):
        return ExtensionIndexer

    def get_minifest_contents(self, force=False):
        raise NotImplementedError

    def get_package_path(self):
        raise NotImplementedError

    def handle_file_operations(self, upload):
        """Copy the file attached to a FileUpload to the Extension instance."""
        upload.path = smart_path(nfd_str(upload.path))

        if not self.slug:
            raise RuntimeError(
                'Trying to upload a file belonging to a slugless extension')

        if private_storage.exists(self.file_path):
            # The filename should not exist. If it does, it means we are trying
            # to re-upload the same version. This should have been caught
            # before, so just raise an exception.
            raise RuntimeError(
                'Trying to upload a file to a destination that already exists')

        # Copy file from fileupload. This uses private_storage for now as the
        # unreviewed, unsigned filename is private.
        copy_stored_file(upload.path, self.file_path)

    def is_public(self):
        return self.status == STATUS_PUBLIC

    @property
    def manifest_url(self):
        raise NotImplementedError

    def publish(self):
        """Publish this add-on to public."""
        self.sign_and_move_file()
        self.update(status=STATUS_PUBLIC)

    def reject(self):
        """Reject this add-on."""
        self.update(status=STATUS_REJECTED)
        self.remove_signed_file()

    def remove_signed_file(self):
        if public_storage.exists(self.signed_file_path):
            public_storage.delete(self.signed_file_path)

    def sign_and_move_file(self):
        """Sign and move extension file from the unsigned path (`file_path`) on
        private storage to the signed path (`signed_file_path`) on public
        storage."""
        if not self.uuid:
            raise SigningError('Need uuid to be set to sign')

        ids = json.dumps({
            # 'id' needs to be an unique identifier not shared with anything
            # else (other extensions, langpacks, webapps...), but should not
            # change when there is an update.
            'id': self.uuid,
            # 'version' should be an integer and should be monotonically
            # increasing.
            'version': self.file_version
        })
        with statsd.timer('extensions.sign'):
            try:
                # This will read the file from self.file_path, generate a
                # signature and write the signed file to self.signed_file_path.
                sign_app(private_storage.open(self.file_path),
                         self.signed_file_path, ids)
            except SigningError:
                log.info('[Extension:%s] Signing failed' % self.pk)
                self.remove_signed_file()  # Clean up.
                raise

    @property
    def signed_file_path(self):
        prefix = os.path.join(settings.ADDONS_PATH, 'extensions-signed',
                              str(self.pk))
        return os.path.join(prefix, nfd_str(self.filename))

    def save(self, *args, **kwargs):
        if not self.slug:
            self.clean_slug()
        return super(Extension, self).save(*args, **kwargs)

    def __unicode__(self):
        return u'%s: %s' % (self.pk, self.name)


# Maintain ElasticSearch index.
@receiver(models.signals.post_save, sender=Extension,
          dispatch_uid='extension_index')
def update_search_index(sender, instance, **kw):
    instance.get_indexer().index_ids([instance.id])


# Delete from ElasticSearch index on delete.
@receiver(models.signals.post_delete, sender=Extension,
          dispatch_uid='extension_unindex')
def delete_search_index(sender, instance, **kw):
    instance.get_indexer().unindex(instance.id)


# Save translations before saving Extensions instances with translated fields.
models.signals.pre_save.connect(save_signal, sender=Extension,
                                dispatch_uid='extension_translations')

# Delete files when deleting Extension instances.
models.signals.post_delete.connect(cleanup_file, sender=Extension,
                                   dispatch_uid='extension_cleanup_file')
