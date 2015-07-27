# -*- coding: utf-8 -*-
import datetime
import json
import os

import django.dispatch
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.storage import default_storage as storage
from django.db import models

import commonware.log
import jinja2

import mkt
from mkt.files import utils
from mkt.files.models import cleanup_file, File
from mkt.site.decorators import use_master
from mkt.site.models import ManagerBase, ModelBase
from mkt.site.utils import cached_property, sorted_groupby
from mkt.translations.fields import PurifiedField, save_signal
from mkt.versions.tasks import update_supported_locales_single
from mkt.webapps import query


log = commonware.log.getLogger('z.versions')


class VersionManager(ManagerBase):

    def __init__(self, include_deleted=False):
        ManagerBase.__init__(self)
        self.include_deleted = include_deleted

    def get_queryset(self):
        qs = super(VersionManager, self).get_queryset()
        qs = qs._clone(klass=query.IndexQuerySet)
        if not self.include_deleted:
            qs = qs.exclude(deleted=True)
        return qs.transform(Version.transformer)


class Version(ModelBase):
    addon = models.ForeignKey('webapps.Webapp', related_name='versions')
    releasenotes = PurifiedField()
    approvalnotes = models.TextField(default='', null=True)
    version = models.CharField(max_length=255, default='0.1')

    nomination = models.DateTimeField(null=True)
    reviewed = models.DateTimeField(null=True)

    has_info_request = models.BooleanField(default=False)
    has_editor_comment = models.BooleanField(default=False)

    deleted = models.BooleanField(default=False)

    supported_locales = models.CharField(max_length=255)

    _developer_name = models.CharField(max_length=255, default='',
                                       editable=False)

    objects = VersionManager()
    with_deleted = VersionManager(include_deleted=True)

    class Meta(ModelBase.Meta):
        db_table = 'versions'
        ordering = ['-created', '-modified']

    def __init__(self, *args, **kwargs):
        super(Version, self).__init__(*args, **kwargs)

    def __unicode__(self):
        return jinja2.escape(self.version)

    def save(self, *args, **kw):
        creating = not self.id
        super(Version, self).save(*args, **kw)
        if creating:
            # To avoid circular import.
            from mkt.webapps.models import AppFeatures
            AppFeatures.objects.create(version=self)
        return self

    @classmethod
    def from_upload(cls, upload, addon, send_signal=True):
        data = utils.parse_addon(upload, addon)
        max_len = cls._meta.get_field_by_name('_developer_name')[0].max_length
        developer = data.get('developer_name', '')[:max_len]
        v = cls.objects.create(addon=addon, version=data['version'],
                               _developer_name=developer)
        log.info('New version: %r (%s) from %r' % (v, v.id, upload))

        # To avoid circular import.
        from mkt.webapps.models import AppManifest

        # Note: This must happen before we call `File.from_upload`.
        manifest = utils.WebAppParser().get_json_data(upload)
        AppManifest.objects.create(
            version=v, manifest=json.dumps(manifest))

        File.from_upload(upload, v, parse_data=data)

        # Update supported locales from manifest.
        # Note: This needs to happen after we call `File.from_upload`.
        update_supported_locales_single.apply_async(
            args=[addon.id], kwargs={'latest': True},
            eta=datetime.datetime.now() +
            datetime.timedelta(seconds=settings.NFS_LAG_DELAY)
        )

        v.disable_old_files()
        # After the upload has been copied, remove the upload.
        storage.delete(upload.path)
        if send_signal:
            version_uploaded.send(sender=v)

        # If packaged app and app is blocked, put in escalation queue.
        if addon.is_packaged and addon.status == mkt.STATUS_BLOCKED:
            # To avoid circular import.
            from mkt.reviewers.models import EscalationQueue
            EscalationQueue.objects.create(addon=addon)

        return v

    @property
    def path_prefix(self):
        return os.path.join(settings.ADDONS_PATH, str(self.addon_id))

    def delete(self):
        log.info(u'Version deleted: %r (%s)' % (self, self.id))
        mkt.log(mkt.LOG.DELETE_VERSION, self.addon, str(self.version))

        models.signals.pre_delete.send(sender=Version, instance=self)

        was_current = False
        if self == self.addon.current_version:
            was_current = True

        self.update(deleted=True)

        # Set file status to disabled.
        f = self.all_files[0]
        f.update(status=mkt.STATUS_DISABLED, _signal=False)
        f.hide_disabled_file()

        # If version deleted was the current version and there now exists
        # another current_version, we need to call some extra methods to update
        # various bits for packaged apps.
        if was_current and self.addon.current_version:
            self.addon.update_name_from_package_manifest()
            self.addon.update_supported_locales()

        if self.addon.is_packaged:
            # Unlink signed packages if packaged app.
            storage.delete(f.signed_file_path)
            log.info(u'Unlinked file: %s' % f.signed_file_path)
            storage.delete(f.signed_reviewer_file_path)
            log.info(u'Unlinked file: %s' % f.signed_reviewer_file_path)

        models.signals.post_delete.send(sender=Version, instance=self)

    @cached_property(writable=True)
    def all_activity(self):
        from mkt.developers.models import VersionLog
        al = (VersionLog.objects.filter(version=self.id).order_by('created')
              .select_related('activity_log', 'version'))
        return al

    @cached_property(writable=True)
    def all_files(self):
        """Shortcut for list(self.files.all()).  Heavily cached."""
        return list(self.files.all())

    @property
    def status(self):
        status_choices = mkt.MKT_STATUS_FILE_CHOICES

        if self.deleted:
            return [status_choices[mkt.STATUS_DELETED]]
        else:
            return [status_choices[f.status] for f in self.all_files]

    @property
    def statuses(self):
        """Unadulterated statuses, good for an API."""
        return [(f.id, f.status) for f in self.all_files]

    def is_public(self):
        # To be public, a version must not be deleted, must belong to a public
        # addon, and all its attached files must have public status.
        try:
            return (not self.deleted and self.addon.is_public() and
                    all(f.status == mkt.STATUS_PUBLIC for f in self.all_files))
        except ObjectDoesNotExist:
            return False

    @property
    def has_files(self):
        return bool(self.all_files)

    @classmethod
    def transformer(cls, versions):
        """Attach all the files to the versions."""
        ids = set(v.id for v in versions)
        if not versions:
            return

        def rollup(xs):
            groups = sorted_groupby(xs, 'version_id')
            return dict((k, list(vs)) for k, vs in groups)

        file_dict = rollup(File.objects.filter(version__in=ids))

        for version in versions:
            v_id = version.id
            version.all_files = file_dict.get(v_id, [])
            for f in version.all_files:
                f.version = version

    @classmethod
    def transformer_activity(cls, versions):
        """Attach all the activity to the versions."""
        from mkt.developers.models import VersionLog

        ids = set(v.id for v in versions)
        if not versions:
            return

        al = (VersionLog.objects.filter(version__in=ids).order_by('created')
              .select_related('activity_log', 'version'))

        def rollup(xs):
            groups = sorted_groupby(xs, 'version_id')
            return dict((k, list(vs)) for k, vs in groups)

        al_dict = rollup(al)

        for version in versions:
            v_id = version.id
            version.all_activity = al_dict.get(v_id, [])

    def disable_old_files(self):
        qs = File.objects.filter(version__addon=self.addon_id,
                                 version__lt=self.id,
                                 version__deleted=False,
                                 status__in=[mkt.STATUS_PENDING])
        # Use File.update so signals are triggered.
        for f in qs:
            f.update(status=mkt.STATUS_DISABLED)

    @property
    def developer_name(self):
        return self._developer_name

    @cached_property(writable=True)
    def is_privileged(self):
        """
        Return whether the corresponding addon is privileged by looking at
        the manifest file.

        This is a cached property, to avoid going in the manifest more than
        once for a given instance. It's also directly writable do allow you to
        bypass the manifest fetching if you *know* your app is privileged or
        not already and want to pass the instance to some code that will use
        that property.
        """
        if not self.addon.is_packaged or not self.all_files:
            return False
        data = self.addon.get_manifest_json(file_obj=self.all_files[0])
        return data.get('type') == 'privileged'

    @cached_property
    def manifest(self):
        # To avoid circular import.
        from mkt.webapps.models import AppManifest

        try:
            manifest = self.manifest_json.manifest
        except AppManifest.DoesNotExist:
            manifest = None

        return json.loads(manifest) if manifest else {}


@use_master
def update_status(sender, instance, **kw):
    if not kw.get('raw'):
        try:
            instance.addon.reload()
            instance.addon.update_status()
            instance.addon.update_version()
        except models.ObjectDoesNotExist:
            log.info('Got ObjectDoesNotExist processing Version change signal',
                     exc_info=True)
            pass


def inherit_nomination(sender, instance, **kw):
    """Inherit nomination date for new packaged app versions."""
    if kw.get('raw'):
        return
    addon = instance.addon
    if addon.is_packaged:
        # If prior version's file is pending, inherit nomination. Otherwise,
        # set nomination to now.
        last_ver = (Version.objects.filter(addon=addon)
                                   .exclude(pk=instance.pk)
                                   .order_by('-nomination'))
        if (last_ver.exists() and
                last_ver[0].all_files[0].status == mkt.STATUS_PENDING):
            instance.update(nomination=last_ver[0].nomination, _signal=False)
            log.debug('[Webapp:%s] Inheriting nomination from prior pending '
                      'version' % addon.id)
        elif (addon.status in mkt.WEBAPPS_APPROVED_STATUSES and
              not instance.nomination):
            log.debug('[Webapp:%s] Setting nomination date to now for new '
                      'version.' % addon.id)
            instance.update(nomination=datetime.datetime.now(), _signal=False)


def cleanup_version(sender, instance, **kw):
    """On delete of the version object call the file delete and signals."""
    if kw.get('raw'):
        return
    for file_ in instance.files.all():
        cleanup_file(file_.__class__, file_)


version_uploaded = django.dispatch.Signal()
models.signals.pre_save.connect(
    save_signal, sender=Version, dispatch_uid='version_translations')
models.signals.post_save.connect(
    update_status, sender=Version, dispatch_uid='version_update_status')
models.signals.post_save.connect(
    inherit_nomination, sender=Version,
    dispatch_uid='version_inherit_nomination')
models.signals.post_delete.connect(
    update_status, sender=Version, dispatch_uid='version_update_status')
models.signals.pre_delete.connect(
    cleanup_version, sender=Version, dispatch_uid='cleanup_version')
