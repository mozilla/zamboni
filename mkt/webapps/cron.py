import logging
import os
import shutil
import stat
import time
from datetime import datetime, timedelta

from django.conf import settings
from django.db.models import Q

import commonware.log
import cronjobs
import path
from celery import chord

import amo
from amo.decorators import write
from amo.utils import chunked
from mkt.api.models import Nonce
from mkt.developers.models import ActivityLog
from mkt.files.models import File

from .models import Addon, Installed, Webapp
from .tasks import (dump_user_installs, update_downloads, update_trending,
                    zip_users)


log = commonware.log.getLogger('z.cron')
task_log = logging.getLogger('z.task')


def _change_last_updated(next):
    # We jump through some hoops here to make sure we only change the add-ons
    # that really need it, and to invalidate properly.
    current = dict(Addon.objects.values_list('id', 'last_updated'))
    changes = {}

    for addon, last_updated in next.items():
        try:
            if current[addon] != last_updated:
                changes[addon] = last_updated
        except KeyError:
            pass

    if not changes:
        return

    log.debug('Updating %s add-ons' % len(changes))
    # Update + invalidate.
    qs = Addon.objects.no_cache().filter(id__in=changes).no_transforms()
    for addon in qs:
        addon.last_updated = changes[addon.id]
        addon.save()


@cronjobs.register
@write
def addon_last_updated():
    next = {}
    qs = Addon._last_updated_queries().values()
    for addon, last_updated in qs.values_list('id', 'last_updated'):
        next[addon] = last_updated

    _change_last_updated(next)

    # Get anything that didn't match above.
    other = (Addon.objects.no_cache().filter(last_updated__isnull=True)
             .values_list('id', 'created'))
    _change_last_updated(dict(other))


@cronjobs.register
def addons_add_slugs():
    """Give slugs to any slugless addons."""
    Addon._meta.get_field('modified').auto_now = False
    q = Addon.objects.filter(slug=None).order_by('id')

    # Chunk it so we don't do huge queries.
    for chunk in chunked(q, 300):
        task_log.info('Giving slugs to %s slugless addons' % len(chunk))
        for addon in chunk:
            addon.save()


@cronjobs.register
def hide_disabled_files():
    # If an add-on or a file is disabled, it should be moved to
    # GUARDED_ADDONS_PATH so it's not publicly visible.
    #
    # We ignore deleted versions since we hide those files when deleted and
    # also due to bug 980916.
    ids = (File.objects
           .filter(version__deleted=False)
           .filter(Q(status=amo.STATUS_DISABLED) |
                   Q(version__addon__status=amo.STATUS_DISABLED) |
                   Q(version__addon__disabled_by_user=True))
           .values_list('id', flat=True))
    for chunk in chunked(ids, 300):
        qs = File.objects.no_cache().filter(id__in=chunk)
        qs = qs.select_related('version')
        for f in qs:
            f.hide_disabled_file()


@cronjobs.register
def unhide_disabled_files():
    # Files are getting stuck in /guarded-addons for some reason. This job
    # makes sure guarded add-ons are supposed to be disabled.
    log = logging.getLogger('z.files.disabled')
    q = (Q(version__addon__status=amo.STATUS_DISABLED)
         | Q(version__addon__disabled_by_user=True))
    files = set(File.objects.filter(q | Q(status=amo.STATUS_DISABLED))
                .values_list('version__addon', 'filename'))
    for filepath in path.path(settings.GUARDED_ADDONS_PATH).walkfiles():
        addon, filename = filepath.split('/')[-2:]
        if tuple([int(addon), filename]) not in files:
            log.warning('File that should not be guarded: %s.' % filepath)
            try:
                file_ = (File.objects.select_related('version__addon')
                         .get(version__addon=addon, filename=filename))
                file_.unhide_disabled_file()
            except File.DoesNotExist:
                log.warning('File object does not exist for: %s.' % filepath)
            except Exception:
                log.error('Could not unhide file: %s.' % filepath,
                          exc_info=True)


@cronjobs.register
def clean_old_signed(seconds=60 * 60):
    """Clean out apps signed for reviewers."""
    log.info('Removing old apps signed for reviewers')
    root = settings.SIGNED_APPS_REVIEWER_PATH
    for path in os.listdir(root):
        full = os.path.join(root, path)
        age = time.time() - os.stat(full)[stat.ST_ATIME]
        if age > seconds:
            log.debug('Removing signed app: %s, %dsecs old.' % (full, age))
            shutil.rmtree(full)


@cronjobs.register
def update_app_trending():
    """
    Update trending for all apps.

    Spread these tasks out successively by 15 seconds so they don't hit
    Monolith all at once.

    """
    chunk_size = 50
    seconds_between = 15

    all_ids = list(Webapp.objects.filter(status=amo.STATUS_PUBLIC)
                   .values_list('id', flat=True))

    countdown = 0
    for ids in chunked(all_ids, chunk_size):
        update_trending.delay(ids, countdown=countdown)
        countdown += seconds_between


@cronjobs.register
def dump_user_installs_cron():
    """
    Sets up tasks to do user install dumps.
    """
    chunk_size = 100
    # Get valid users to dump.
    user_ids = set(Installed.objects.filter(addon__type=amo.ADDON_WEBAPP)
                   .values_list('user', flat=True))

    # Remove old dump data before running.
    user_dir = os.path.join(settings.DUMPED_USERS_PATH, 'users')
    if os.path.exists(user_dir):
        shutil.rmtree(user_dir)

    grouping = []
    for chunk in chunked(user_ids, chunk_size):
        grouping.append(dump_user_installs.subtask(args=[chunk]))

    post = zip_users.subtask(immutable=True)
    ts = chord(grouping, post)
    ts.apply_async()


@cronjobs.register
def update_app_downloads():
    """
    Update download/install stats for all apps.

    Spread these tasks out successively by `seconds_between` seconds so they
    don't hit Monolith all at once.

    """
    chunk_size = 50
    seconds_between = 2

    all_ids = list(Webapp.objects.filter(status=amo.STATUS_PUBLIC)
                   .values_list('id', flat=True))

    countdown = 0
    for ids in chunked(all_ids, chunk_size):
        update_downloads.delay(ids, countdown=countdown)
        countdown += seconds_between


@cronjobs.register
def mkt_gc(**kw):
    """Site-wide garbage collections."""
    days_ago = lambda days: datetime.today() - timedelta(days=days)

    log.debug('Collecting data to delete')
    logs = (ActivityLog.objects.filter(created__lt=days_ago(90))
            .exclude(action__in=amo.LOG_KEEP).values_list('id', flat=True))

    for chunk in chunked(logs, 100):
        chunk.sort()
        log.debug('Deleting log entries: %s' % str(chunk))
        amo.tasks.delete_logs.delay(chunk)

    # Clear oauth nonce rows. These expire after 10 minutes but we're just
    # clearing those that are more than 1 day old.
    Nonce.objects.filter(created__lt=days_ago(1)).delete()

    # Delete the dump apps over 30 days.
    for app in os.listdir(settings.DUMPED_APPS_PATH):
        app = os.path.join(settings.DUMPED_APPS_PATH, app)
        if (os.stat(app).st_mtime < time.time() -
            settings.DUMPED_APPS_DAYS_DELETE):
            log.debug('Deleting old tarball: {0}'.format(app))
            os.remove(app)

    # Delete the dumped user installs over 30 days.
    tarball_path = os.path.join(settings.DUMPED_USERS_PATH, 'tarballs')
    for filename in os.listdir(tarball_path):
        filepath = os.path.join(tarball_path, filename)
        if (os.stat(filepath).st_mtime < time.time() -
            settings.DUMPED_USERS_DAYS_DELETE):
            log.debug('Deleting old tarball: {0}'.format(filepath))
            os.remove(filepath)
