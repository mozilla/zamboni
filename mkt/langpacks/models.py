 # -*- coding: utf-8 -*-
import hashlib
import os.path

from django.conf import settings
from django.core.files.storage import default_storage as storage
from django.db import models
from django.utils.functional import lazy

import commonware.log
from uuidfield.fields import UUIDField

from mkt.files.models import cleanup_file, nfd_str
from mkt.langpacks.utils import LanguagePackParser
from mkt.site.models import ModelBase
from mkt.site.storage_utils import copy_stored_file
from mkt.site.utils import smart_path


log = commonware.log.getLogger('z.versions')


LANGUAGE_CHOICES = lazy(lambda l: dict(l).items(), list)(settings.LANGUAGES)


class LangPack(ModelBase):
    # Primary key is a uuid in order to be able to set it in advance (we need
    # something unique for the filename, and we don't have a slug).
    uuid = UUIDField(primary_key=True, auto=True)

    # Fields for which the manifest is the source of truth - can't be
    # overridden by the API.
    language = models.CharField(choices=LANGUAGE_CHOICES,
                                default=settings.LANGUAGE_CODE, max_length=10)
    fxos_version = models.CharField(max_length=255, default='')
    version = models.CharField(max_length=255, default='')

    # Automatically generated fields.
    filename = models.CharField(max_length=255, default='')
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
        # FIXME: store validation result ?
        upload.path = smart_path(nfd_str(upload.path))
        if not self.uuid:
            self.reset_uuid()
        self.filename = self.generate_filename()
        self.size = storage.size(upload.path)  # Size in bytes.
        self.hash = self.generate_hash(upload.path)
        copy_stored_file(upload.path, self.file_path)

    @classmethod
    def from_upload(cls, upload, instance=None):
        """Handle creating/editing the LangPack instance and saving it to db,
        as well as file operations, from a FileUpload instance. Can throw
        a ValidationError, so should always be called within a try/except."""
        data = LanguagePackParser().parse(upload)
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
