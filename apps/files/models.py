import hashlib
import json
import os
import unicodedata
import uuid

from django.conf import settings
from django.core.files.storage import default_storage as storage
from django.db import models
from django.dispatch import receiver
from django.template.defaultfilters import slugify
from django.utils.encoding import smart_str

import commonware
from uuidfield.fields import UUIDField

import amo
import amo.models
import amo.utils
from amo.decorators import use_master
from amo.storage_utils import copy_stored_file, move_stored_file
from amo.urlresolvers import reverse


log = commonware.log.getLogger('z.files')


# Acceptable extensions.
EXTENSIONS = ('.webapp', '.json', '.zip')


class File(amo.models.OnChangeMixin, amo.models.ModelBase):
    STATUS_CHOICES = amo.STATUS_CHOICES.items()

    version = models.ForeignKey('versions.Version', related_name='files')
    platform = models.ForeignKey('Platform', default=amo.PLATFORM_ALL.id)
    filename = models.CharField(max_length=255, default='')
    size = models.PositiveIntegerField(default=0)  # In bytes.
    hash = models.CharField(max_length=255, default='')
    status = models.PositiveSmallIntegerField(choices=STATUS_CHOICES,
                                              default=amo.STATUS_UNREVIEWED)
    datestatuschanged = models.DateTimeField(null=True, auto_now_add=True)
    reviewed = models.DateTimeField(null=True)
    # Whether a webapp uses flash or not.
    uses_flash = models.BooleanField(default=False, db_index=True)

    class Meta(amo.models.ModelBase.Meta):
        db_table = 'files'

    def __unicode__(self):
        return unicode(self.id)

    @property
    def amo_platform(self):
        # TODO: Ideally this would be ``platform``.
        return amo.PLATFORMS[self.platform_id]

    @property
    def has_been_validated(self):
        try:
            self.validation
        except FileValidation.DoesNotExist:
            return False
        else:
            return True

    def get_url_path(self, src):
        from amo.helpers import urlparams, absolutify
        url = os.path.join(reverse('downloads.file', args=[self.id]),
                           self.filename)
        # Firefox's Add-on Manager needs absolute urls.
        return absolutify(urlparams(url, src=src))

    @classmethod
    def from_upload(cls, upload, version, platform, parse_data={}):
        upload.path = amo.utils.smart_path(nfd_str(upload.path))
        ext = os.path.splitext(upload.path)[1]

        f = cls(version=version, platform=platform)
        f.filename = f.generate_filename(extension=ext or '.zip')
        f.size = storage.size(upload.path)  # Size in bytes.
        f.status = amo.STATUS_PENDING
        f.hash = f.generate_hash(upload.path)
        f.save()

        log.debug('New file: %r from %r' % (f, upload))

        # Move the uploaded file from the temp location.
        copy_stored_file(upload.path, os.path.join(version.path_prefix,
                                                   nfd_str(f.filename)))
        if upload.validation:
            FileValidation.from_json(f, upload.validation)

        return f

    def generate_hash(self, filename=None):
        """Generate a hash for a file."""
        hash = hashlib.sha256()
        with open(filename or self.file_path, 'rb') as obj:
            for chunk in iter(lambda: obj.read(1024), ''):
                hash.update(chunk)
        return 'sha256:%s' % hash.hexdigest()

    def generate_filename(self, extension=None):
        """
        Files are in the format of: {app_slug}-{version}.{extension}
        """
        parts = []
        addon = self.version.addon
        # slugify drops unicode so we may end up with an empty string.
        # Apache did not like serving unicode filenames (bug 626587).
        extension = extension or '.zip' if addon.is_packaged else '.webapp'
        # Apparently we have non-ascii slugs leaking into prod :(
        # FIXME.
        parts.append(slugify(addon.app_slug) or 'app')
        parts.append(self.version.version)

        self.filename = '-'.join(parts) + extension
        return self.filename

    @property
    def file_path(self):
        return os.path.join(settings.ADDONS_PATH, str(self.version.addon_id),
                            self.filename)

    @property
    def addon(self):
        from mkt.versions.models import Version
        from mkt.webapps.models import Addon

        version = Version.with_deleted.get(pk=self.version_id)
        return Addon.with_deleted.get(pk=version.addon_id)

    @property
    def guarded_file_path(self):
        return os.path.join(settings.GUARDED_ADDONS_PATH,
                            str(self.version.addon_id), self.filename)

    def _signed(self):
        split = self.filename.rsplit('.', 1)
        split.insert(-1, 'signed')
        return '.'.join(split)

    @property
    def signed_file_path(self):
        return os.path.join(settings.SIGNED_APPS_PATH,
                            str(self.version.addon_id), self._signed())

    @property
    def signed_reviewer_file_path(self):
        return os.path.join(settings.SIGNED_APPS_REVIEWER_PATH,
                            str(self.version.addon_id), self._signed())

    @property
    def extension(self):
        return os.path.splitext(self.filename)[-1]

    @classmethod
    def mv(cls, src, dst, msg):
        """Move a file from src to dst."""
        try:
            if storage.exists(src):
                log.info(msg % (src, dst))
                move_stored_file(src, dst)
        except UnicodeEncodeError:
            log.error('Move Failure: %s %s' % (smart_str(src), smart_str(dst)))

    def hide_disabled_file(self):
        """Move a disabled file to the guarded file path."""
        if not self.filename:
            return
        src, dst = self.file_path, self.guarded_file_path
        self.mv(src, dst, 'Moving disabled file: %s => %s')

    def unhide_disabled_file(self):
        if not self.filename:
            return
        src, dst = self.guarded_file_path, self.file_path
        self.mv(src, dst, 'Moving undisabled file: %s => %s')


@use_master
def update_status(sender, instance, **kw):
    if not kw.get('raw'):
        try:
            instance.version.addon.reload()
            instance.version.addon.update_status()
            if 'delete' in kw:
                instance.version.addon.update_version(ignore=instance.version)
            else:
                instance.version.addon.update_version()
        except models.ObjectDoesNotExist:
            pass


def update_status_delete(sender, instance, **kw):
    kw['delete'] = True
    return update_status(sender, instance, **kw)


models.signals.post_save.connect(
    update_status, sender=File, dispatch_uid='version_update_status')
models.signals.post_delete.connect(
    update_status_delete, sender=File, dispatch_uid='version_update_status')


@receiver(models.signals.post_delete, sender=File,
          dispatch_uid='cleanup_file')
def cleanup_file(sender, instance, **kw):
    """ On delete of the file object from the database, unlink the file from
    the file system """
    if kw.get('raw') or not instance.filename:
        return
    # Use getattr so the paths are accessed inside the try block.
    for path in ('file_path', 'guarded_file_path'):
        try:
            filename = getattr(instance, path)
        except models.ObjectDoesNotExist:
            return
        if storage.exists(filename):
            log.info('Removing filename: %s for file: %s'
                     % (filename, instance.pk))
            storage.delete(filename)


@File.on_change
def check_file(old_attr, new_attr, instance, sender, **kw):
    if kw.get('raw'):
        return
    old, new = old_attr.get('status'), instance.status
    if new == amo.STATUS_DISABLED and old != amo.STATUS_DISABLED:
        instance.hide_disabled_file()
    elif old == amo.STATUS_DISABLED and new != amo.STATUS_DISABLED:
        instance.unhide_disabled_file()

    # Log that the hash has changed.
    old, new = old_attr.get('hash'), instance.hash
    if old != new:
        try:
            addon = instance.version.addon.pk
        except models.ObjectDoesNotExist:
            addon = 'unknown'
        log.info('Hash changed for file: %s, addon: %s, from: %s to: %s' %
                 (instance.pk, addon, old, new))


class Platform(amo.models.ModelBase):
    # `name` and `shortname` are provided in amo.__init__
    # name = TranslatedField()
    # shortname = TranslatedField()

    class Meta(amo.models.ModelBase.Meta):
        db_table = 'platforms'

    def __unicode__(self):
        if self.id in amo.PLATFORMS:
            return unicode(amo.PLATFORMS[self.id].name)
        else:
            log.warning('Invalid platform')
            return ''


class FileUpload(amo.models.ModelBase):
    """Created when a file is uploaded for validation/submission."""
    uuid = UUIDField(primary_key=True, auto=True)
    path = models.CharField(max_length=255, default='')
    name = models.CharField(max_length=255, default='',
                            help_text="The user's original filename")
    hash = models.CharField(max_length=255, default='')
    user = models.ForeignKey('users.UserProfile', null=True)
    valid = models.BooleanField(default=False)
    is_webapp = models.BooleanField(default=False)
    validation = models.TextField(null=True)
    task_error = models.TextField(null=True)

    objects = amo.models.UncachedManagerBase()

    class Meta(amo.models.ModelBase.Meta):
        db_table = 'file_uploads'

    def __unicode__(self):
        return self.uuid

    def save(self, *args, **kw):
        if self.validation:
            try:
                if json.loads(self.validation)['errors'] == 0:
                    self.valid = True
            except Exception:
                log.error('Invalid validation json: %r' % self)
        super(FileUpload, self).save()

    def add_file(self, chunks, filename, size, is_webapp=False):
        filename = smart_str(filename)
        loc = os.path.join(settings.ADDONS_PATH, 'temp', uuid.uuid4().hex)
        base, ext = os.path.splitext(amo.utils.smart_path(filename))
        if ext in EXTENSIONS:
            loc += ext
        log.info('UPLOAD: %r (%s bytes) to %r' % (filename, size, loc))
        hash = hashlib.sha256()
        with storage.open(loc, 'wb') as fd:
            for chunk in chunks:
                hash.update(chunk)
                fd.write(chunk)
        self.path = loc
        self.name = filename
        self.hash = 'sha256:%s' % hash.hexdigest()
        self.is_webapp = is_webapp
        self.save()

    @classmethod
    def from_post(cls, chunks, filename, size, is_webapp=False):
        fu = FileUpload()
        fu.add_file(chunks, filename, size, is_webapp)
        return fu

    @property
    def processed(self):
        return bool(self.valid or self.validation)


class FileValidation(amo.models.ModelBase):
    file = models.OneToOneField(File, related_name='validation')
    valid = models.BooleanField(default=False)
    errors = models.IntegerField(default=0)
    warnings = models.IntegerField(default=0)
    notices = models.IntegerField(default=0)
    validation = models.TextField()

    class Meta:
        db_table = 'file_validation'

    @classmethod
    def from_json(cls, file, validation):
        js = json.loads(validation)
        new = cls(file=file, validation=validation, errors=js['errors'],
                  warnings=js['warnings'], notices=js['notices'])
        new.valid = new.errors == 0
        new.save()
        return new


def nfd_str(u):
    """Uses NFD to normalize unicode strings."""
    if isinstance(u, unicode):
        return unicodedata.normalize('NFD', u).encode('utf-8')
    return u
