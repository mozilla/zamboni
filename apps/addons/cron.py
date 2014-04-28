import array
import itertools
import logging
import operator
import os
import subprocess
import time
from datetime import datetime, timedelta

from django.conf import settings
from django.db import connections, transaction
from django.db.models import Q, F

import cronjobs
import multidb
import path
from celery.task.sets import TaskSet
from celeryutils import task
import waffle

import amo
from amo.decorators import write
from amo.utils import chunked
from addons.models import Addon, AppSupport
from files.models import File


log = logging.getLogger('z.cron')
task_log = logging.getLogger('z.task')
recs_log = logging.getLogger('z.recs')


# TODO(jbalogh): removed from cron on 6/27/11. If the site doesn't break,
# delete it.
@cronjobs.register
def fast_current_version():

    # Candidate for deletion - Bug 750510
    if not waffle.switch_is_active('current_version_crons'):
        return
    # Only find the really recent versions; this is called a lot.
    t = datetime.now() - timedelta(minutes=5)
    qs = Addon.objects.values_list('id')
    q1 = qs.filter(status=amo.STATUS_PUBLIC,
                   versions__files__datestatuschanged__gte=t)
    q2 = qs.filter(status__in=amo.UNREVIEWED_STATUSES,
                   versions__files__created__gte=t)
    addons = set(q1) | set(q2)
    if addons:
        _update_addons_current_version(addons)


# TODO(jbalogh): removed from cron on 6/27/11. If the site doesn't break,
# delete it.
@cronjobs.register
def update_addons_current_version():
    """Update the current_version field of the addons."""

    # Candidate for deletion - Bug 750510
    if not waffle.switch_is_active('current_version_crons'):
        return

    d = (Addon.objects.filter(disabled_by_user=False,
                              status__in=amo.VALID_STATUSES)
         .exclude(type=amo.ADDON_PERSONA).values_list('id'))

    ts = [_update_addons_current_version.subtask(args=[chunk])
          for chunk in chunked(d, 100)]
    TaskSet(ts).apply_async()


# TODO(jbalogh): removed from cron on 6/27/11. If the site doesn't break,
# delete it.
@task(rate_limit='20/m')
def _update_addons_current_version(data, **kw):

    # Candidate for deletion - Bug 750510
    if not waffle.switch_is_active('current_version_crons'):
        return

    task_log.info("[%s@%s] Updating addons current_versions." %
                   (len(data), _update_addons_current_version.rate_limit))
    for pk in data:
        try:
            addon = Addon.objects.get(pk=pk[0])
            addon.update_version()
        except Addon.DoesNotExist:
            m = "Failed to update current_version. Missing add-on: %d" % (pk)
            task_log.debug(m)
    transaction.commit_unless_managed()


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
    for q in Addon._last_updated_queries().values():
        for addon, last_updated in q.values_list('id', 'last_updated'):
            next[addon] = last_updated

    _change_last_updated(next)

    # Get anything that didn't match above.
    other = (Addon.objects.no_cache().filter(last_updated__isnull=True)
             .values_list('id', 'created'))
    _change_last_updated(dict(other))


@cronjobs.register
def update_addon_appsupport():
    # Find all the add-ons that need their app support details updated.
    newish = (Q(last_updated__gte=F('appsupport__created')) |
              Q(appsupport__created__isnull=True))
    # Search providers don't list supported apps.
    has_app = Q(versions__apps__isnull=False) | Q(type=amo.ADDON_SEARCH)
    has_file = Q(versions__files__status__in=amo.VALID_STATUSES)
    good = Q(has_app, has_file) | Q(type=amo.ADDON_PERSONA)
    ids = (Addon.objects.valid().distinct()
           .filter(newish, good).values_list('id', flat=True))

    ts = [_update_appsupport.subtask(args=[chunk])
          for chunk in chunked(ids, 20)]
    TaskSet(ts).apply_async()


@cronjobs.register
def update_all_appsupport():
    from .tasks import update_appsupport
    ids = sorted(set(AppSupport.objects.values_list('addon', flat=True)))
    task_log.info('Updating appsupport for %s addons.' % len(ids))
    for idx, chunk in enumerate(chunked(ids, 100)):
        if idx % 10 == 0:
            task_log.info('[%s/%s] Updating appsupport.'
                          % (idx * 100, len(ids)))
        update_appsupport(chunk)


@task
@transaction.commit_manually
def _update_appsupport(ids, **kw):
    from .tasks import update_appsupport
    update_appsupport(ids)


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
    q = (Q(version__addon__status=amo.STATUS_DISABLED)
         | Q(version__addon__disabled_by_user=True))
    ids = (File.objects.filter(q | Q(status=amo.STATUS_DISABLED))
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
                if (file_.version.addon.status in amo.MIRROR_STATUSES
                    and file_.status in amo.MIRROR_STATUSES):
                    file_.copy_to_mirror()
            except File.DoesNotExist:
                log.warning('File object does not exist for: %s.' % filepath)
            except Exception:
                log.error('Could not unhide file: %s.' % filepath,
                          exc_info=True)

