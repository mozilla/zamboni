import os
import shutil
import stat
import time
from datetime import datetime, timedelta

from django.conf import settings

import commonware.log
import cronjobs
from celery import chord

import amo
from amo.utils import chunked
from devhub.models import ActivityLog

from mkt.api.models import Nonce

from .models import Installed, Webapp
from .tasks import (dump_user_installs, update_downloads, update_trending,
                    zip_users)


log = commonware.log.getLogger('z.cron')


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
