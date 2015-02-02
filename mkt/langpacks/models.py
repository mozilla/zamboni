 # -*- coding: utf-8 -*-
import hashlib
import json
import os.path
from uuid import UUID

from django.conf import settings
from django.core.files.storage import default_storage as storage
from django.core.urlresolvers import reverse
from django.db import models
from django.utils.functional import lazy
from django.utils import translation

import commonware.log
from django_statsd.clients import statsd
from tower import ugettext as _
from uuidfield.fields import UUIDField

from lib.crypto.packaged import sign_app, SigningError
from mkt.files.models import cleanup_file, nfd_str
from mkt.langpacks.utils import LanguagePackParser
from mkt.translations.utils import to_language
from mkt.site.helpers import absolutify
from mkt.site.models import ModelBase
from mkt.site.utils import smart_path


log = commonware.log.getLogger('z.versions')


def _make_language_choices(languages):
    return [(to_language(lang_code), lang_name)
            for lang_code, lang_name in languages.items()]


LANGUAGE_CHOICES = lazy(_make_language_choices, list)(settings.LANGUAGES)


class LangPack(ModelBase):
    # Primary key is a uuid in order to be able to set it in advance (we need
    # something unique for the filename, and we don't have a slug).
    uuid = UUIDField(primary_key=True, auto=True)

    # Fields for which the manifest is the source of truth - can't be
    # overridden by the API.
    language = models.CharField(choices=LANGUAGE_CHOICES,
                                default=settings.LANGUAGE_CODE,
                                max_length=10)
    fxos_version = models.CharField(max_length=255, default='')
    version = models.CharField(max_length=255, default='')

    # Automatically generated fields.
    filename = models.CharField(max_length=255, default='')
    file_version = models.PositiveIntegerField(default=0)
    hash = models.CharField(max_length=255, default='')
    size = models.PositiveIntegerField(default=0)  # In bytes.

    # Fields that can be modified using the API.
    active = models.BooleanField(default=False)

    # Note: we don't need to link a LangPack to an user right now, but in the
    # future, if we want to do that, call it user (single owner) or authors
    # (multiple authors) to be compatible with the API permission classes.

    class Meta:
        ordering = (('-created'), )
        index_together = (('fxos_version', 'language', 'active', 'created'),)


    def is_public(self):
        return self.active

    @property
    def path_prefix(self):
        return os.path.join(settings.ADDONS_PATH, 'langpacks', str(self.pk))

    @property
    def file_path(self):
        return os.path.join(self.path_prefix, nfd_str(self.filename))

    @property
    def download_url(self):
        url = ('%s/langpack.zip' %
            reverse('downloads.langpack', args=[unicode(self.pk)]))
        return absolutify(url)

    @property
    def manifest_url(self):
        """Return URL to the minifest for the langpack"""
        if self.active:
            return absolutify(
                reverse('langpack.manifest', args=[unicode(UUID(self.pk))]))
        return ''

    def get_minifest_contents(self):
        """Return generated mini-manifest for the langpack."""
        # For now, langpacks have no icons, their developer name is fixed
        # (Mozilla, we refuse third-party langpacks) and we can generate their
        # name and description, so we don't need to look in the real manifest
        # in the zip file. When we do, we'll need to add caching and refactor
        # to avoid code duplication with mkt.detail.manifest() and
        # mkt.webapps.Webapp.get_cached_manifest().
        with translation.override(self.language):
            name = _('%(lang)s language pack for Firefox OS %(version)s' % {
                'lang': self.get_language_display(),
                'version': self.fxos_version
            })
        manifest = {
            'name': name,
            'developer': {
                'name': 'Mozilla'
            },
            'package_path': self.download_url,
            'size': self.size,
            'version': self.version
        }
        return manifest

    def generate_filename(self):
        return '%s-%s.zip' % (self.uuid, self.version)

    def generate_hash(self, filename=None):
        """Generate a hash for a file."""
        hash = hashlib.sha256()
        with open(filename or self.file_path, 'rb') as obj:
            for chunk in iter(lambda: obj.read(1024), ''):
                hash.update(chunk)
        return 'sha256:%s' % hash.hexdigest()

    def reset_uuid(self):
        self.uuid = self._meta.get_field('uuid')._create_uuid()

    def handle_file_operations(self, upload):
        """Handle file operations on an instance by using the FileUpload object
        passed to set filename, size, hash on the LangPack instance, and moving
        the temporary file to its final destination."""
        upload.path = smart_path(nfd_str(upload.path))
        if not self.uuid:
            self.reset_uuid()
        self.filename = self.generate_filename()
        if storage.exists(self.filename):
            # The filename should not exist. If it does, it means we are trying
            # to re-upload the same version. This should have been caught
            # before, so just raise an exception.
            raise RuntimeError(
                'Trying to upload a file to a destination that already exists')

        self.size = storage.size(upload.path)  # Size in bytes.
        self.hash = self.generate_hash(upload.path)
        self.file_version = self.file_version + 1

        # Because we are only dealing with langpacks generated by Mozilla atm,
        # we can directly sign the file before copying it to its final
        # destination. The filename changes with the version, so when a new
        # file is uploaded we should still be able to serve the old one until
        # the new info is stored in the db.
        self.sign_and_move_file(upload)

    def sign_and_move_file(self, upload):
        ids = json.dumps({
            # 'id' needs to be unique for a given langpack, but should not
            # change when there is an update.
            'id': self.pk,
            # 'version' should be an integer and should be monotonically
            # increasing.
            'version': self.file_version
        })
        with statsd.timer('langpacks.sign'):
            try:
                # This will read the upload.path file, generate a signature
                # and write the signed file to self.file_path.
                sign_app(upload.path, self.file_path, ids)
            except SigningError:
                log.info('[LangPack:%s] Signing failed' % self.pk)
                if storage.exists(self.file_path):
                    storage.delete(self.file_path)
                raise

    @classmethod
    def from_upload(cls, upload, instance=None):
        """Handle creating/editing the LangPack instance and saving it to db,
        as well as file operations, from a FileUpload instance. Can throw
        a ValidationError or SigningError, so should always be called within a
        try/except."""
        data = LanguagePackParser(instance=instance).parse(upload)
        allowed_fields = ('language', 'fxos_version', 'version')
        data = dict((k, v) for k, v in data.items() if k in allowed_fields)
        if instance:
            # If we were passed an instance, override fields on it using the
            # data from the uploaded package.
            instance.__dict__.update(**data)
        else:
            # Build a new instance.
            instance = cls(**data)
        # Do last-minute validation that requires an instance.
        cls._meta.get_field('language').validate(instance.language, instance)
        # Fill in fields depending on the file contents, and move the file.
        instance.handle_file_operations(upload)
        # Save!
        instance.save()
        return instance


models.signals.post_delete.connect(cleanup_file, sender=LangPack,
                                   dispatch_uid='langpack_cleanup_file')
