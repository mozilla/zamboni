import logging
import os
import shutil
import time
from datetime import datetime

from django.conf import settings
from django.db.models import Q

import commonware.log
import cronjobs
from celery import chord

import mkt
from lib.metrics import get_monolith_client
from mkt.api.models import Nonce
from mkt.developers.models import ActivityLog
from mkt.files.models import File, FileUpload
from mkt.site.decorators import use_master
from mkt.site.storage_utils import (private_storage, public_storage,
                                    storage_is_remote, walk_storage)
from mkt.site.utils import chunked, days_ago, walkfiles

from .indexers import WebappIndexer
from .models import Installed, Installs, Trending, Webapp
from .tasks import delete_logs, dump_user_installs, zip_users


log = commonware.log.getLogger('z.cron')
task_log = logging.getLogger('z.task')


def _change_last_updated(next):
    # We jump through some hoops here to make sure we only change the add-ons
    # that really need it, and to invalidate properly.
    current = dict(Webapp.objects.values_list('id', 'last_updated'))
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
    qs = Webapp.objects.filter(id__in=changes).no_transforms()
    for addon in qs:
        addon.last_updated = changes[addon.id]
        addon.save()


@cronjobs.register
@use_master
def addon_last_updated():
    next = {}
    qs = Webapp._last_updated_queries().values()
    for addon, last_updated in qs.values_list('id', 'last_updated'):
        next[addon] = last_updated

    _change_last_updated(next)

    # Get anything that didn't match above.
    other = (Webapp.objects.filter(last_updated__isnull=True)
             .values_list('id', 'created'))
    _change_last_updated(dict(other))


@cronjobs.register
def hide_disabled_files():
    # If an add-on or a file is disabled, it should be moved to
    # GUARDED_ADDONS_PATH so it's not publicly visible.
    #
    # We ignore deleted versions since we hide those files when deleted and
    # also due to bug 980916.
    ids = (File.objects
           .filter(version__deleted=False)
           .filter(Q(status=mkt.STATUS_DISABLED) |
                   Q(version__addon__status=mkt.STATUS_DISABLED) |
                   Q(version__addon__disabled_by_user=True))
           .values_list('id', flat=True))
    for chunk in chunked(ids, 300):
        qs = File.objects.filter(id__in=chunk)
        qs = qs.select_related('version')
        for f in qs:
            f.hide_disabled_file()


@cronjobs.register
def unhide_disabled_files():
    # Files are getting stuck in /guarded-addons for some reason. This job
    # makes sure guarded add-ons are supposed to be disabled.
    log = logging.getLogger('z.files.disabled')
    q = (Q(version__addon__status=mkt.STATUS_DISABLED) |
         Q(version__addon__disabled_by_user=True))
    files = set(File.objects.filter(q | Q(status=mkt.STATUS_DISABLED))
                .values_list('version__addon', 'filename'))
    for filepath in walkfiles(settings.GUARDED_ADDONS_PATH):
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
    # Local storage uses local time for file modification. S3 uses UTC time.
    now = datetime.utcnow if storage_is_remote() else datetime.now
    for nextroot, dirs, files in walk_storage(root):
        for fn in files:
            full = os.path.join(nextroot, fn)
            age = now() - private_storage.modified_time(full)
            if age.total_seconds() > seconds:
                log.debug('Removing signed app: %s, %dsecs old.' % (
                    full, age.total_seconds()))
                private_storage.delete(full)


def _get_installs(app_id):
    """
    Calculate popularity of app for all regions and per region.

    Returns value in the format of::

        {'all': <global installs>,
         <region_slug>: <regional installs>,
         ...}

    """
    # How many days back do we include when calculating popularity.
    POPULARITY_PERIOD = 90

    client = get_monolith_client()

    popular = {
        'filter': {
            'range': {
                'date': {
                    'gte': days_ago(POPULARITY_PERIOD).date().isoformat(),
                    'lte': days_ago(1).date().isoformat()
                }
            }
        },
        'aggs': {
            'total_installs': {
                'sum': {
                    'field': 'app_installs'
                }
            }
        }
    }

    query = {
        'query': {
            'filtered': {
                'query': {'match_all': {}},
                'filter': {'term': {'app-id': app_id}}
            }
        },
        'aggregations': {
            'popular': popular,
            'region': {
                'terms': {
                    'field': 'region',
                    # Add size so we get all regions, not just the top 10.
                    'size': len(mkt.regions.ALL_REGIONS)
                },
                'aggregations': {
                    'popular': popular
                }
            }
        },
        'size': 0
    }

    try:
        res = client.raw(query)
    except ValueError as e:
        task_log.error('Error response from Monolith: {0}'.format(e))
        return {}

    if 'aggregations' not in res:
        task_log.error('No installs for app {}'.format(app_id))
        return {}

    results = {
        'all': res['aggregations']['popular']['total_installs']['value']
    }

    if 'region' in res['aggregations']:
        for regional_res in res['aggregations']['region']['buckets']:
            region_slug = regional_res['key']
            popular = regional_res['popular']['total_installs']['value']
            results[region_slug] = popular

    return results


@cronjobs.register
@use_master
def update_app_installs():
    """
    Update app install counts for all published apps.

    We break these into chunks so we can bulk index them. Each chunk will
    process the apps in it and reindex them in bulk. After all the chunks are
    processed we find records that haven't been updated and purge/reindex those
    so we nullify their values.

    """
    chunk_size = 100

    ids = list(Webapp.objects.filter(status=mkt.STATUS_PUBLIC,
                                     disabled_by_user=False)
                     .values_list('id', flat=True))

    for chunk in chunked(ids, chunk_size):

        count = 0
        times = []
        reindex_ids = []

        for app in Webapp.objects.filter(id__in=chunk).no_transforms():

            reindex = False
            count += 1
            now = datetime.now()
            t_start = time.time()

            scores = _get_installs(app.id)

            # Update global installs, then per-region installs below.
            value = scores.get('all')
            if value > 0:
                reindex = True
                installs, created = app.popularity.get_or_create(
                    region=0, defaults={'value': value})
                if not created:
                    installs.update(value=value, modified=now)
            else:
                # The value is <= 0 so we can just ignore it.
                app.popularity.filter(region=0).delete()

            for region in mkt.regions.REGIONS_DICT.values():
                value = scores.get(region.slug)
                if value > 0:
                    reindex = True
                    installs, created = app.popularity.get_or_create(
                        region=region.id, defaults={'value': value})
                    if not created:
                        installs.update(value=value, modified=now)
                else:
                    # The value is <= 0 so we can just ignore it.
                    app.popularity.filter(region=region.id).delete()

            if reindex:
                reindex_ids.append(app.id)

            times.append(time.time() - t_start)

        # Now reindex the apps that actually have a popularity value.
        if reindex_ids:
            WebappIndexer.run_indexing(reindex_ids)

        log.info('Installs calculated for %s apps. Avg time overall: '
                 '%0.2fs' % (count, sum(times) / count))

    # Purge any records that were not updated.
    #
    # Note: We force update `modified` even if no data changes so any records
    # with older modified times can be purged.
    now = datetime.now()
    midnight = datetime(year=now.year, month=now.month, day=now.day)

    qs = Installs.objects.filter(modified__lte=midnight)
    # First get the IDs so we know what to reindex.
    purged_ids = qs.values_list('addon', flat=True).distinct()
    # Then delete them.
    qs.delete()

    for ids in chunked(purged_ids, chunk_size):
        WebappIndexer.run_indexing(ids)


def _get_trending(app_id):
    """
    Calculate trending for app for all regions and per region.

    a = installs from 8 days ago to 1 day ago
    b = installs from 29 days ago to 9 days ago, averaged per week
    trending = (a - b) / b if a > 100 and b > 1 else 0

    Returns value in the format of::

        {'all': <global trending score>,
         <region_slug>: <regional trending score>,
         ...}

    """
    # How many app installs are required in the prior week to be considered
    # "trending". Adjust this as total Marketplace app installs increases.
    #
    # Note: AMO uses 1000.0 for add-ons.
    PRIOR_WEEK_INSTALL_THRESHOLD = 100.0

    client = get_monolith_client()

    week1 = {
        'filter': {
            'range': {
                'date': {
                    'gte': days_ago(8).date().isoformat(),
                    'lte': days_ago(1).date().isoformat()
                }
            }
        },
        'aggs': {
            'total_installs': {
                'sum': {
                    'field': 'app_installs'
                }
            }
        }
    }
    week3 = {
        'filter': {
            'range': {
                'date': {
                    'gte': days_ago(29).date().isoformat(),
                    'lte': days_ago(9).date().isoformat()
                }
            }
        },
        'aggs': {
            'total_installs': {
                'sum': {
                    'field': 'app_installs'
                }
            }
        }
    }

    query = {
        'query': {
            'filtered': {
                'query': {'match_all': {}},
                'filter': {'term': {'app-id': app_id}}
            }
        },
        'aggregations': {
            'week1': week1,
            'week3': week3,
            'region': {
                'terms': {
                    'field': 'region',
                    # Add size so we get all regions, not just the top 10.
                    'size': len(mkt.regions.ALL_REGIONS)
                },
                'aggregations': {
                    'week1': week1,
                    'week3': week3
                }
            }
        },
        'size': 0
    }

    try:
        res = client.raw(query)
    except ValueError as e:
        task_log.error('Error response from Monolith: {0}'.format(e))
        return {}

    if 'aggregations' not in res:
        task_log.error('No installs for app {}'.format(app_id))
        return {}

    def _score(week1, week3):
        # If last week app installs are < 100, this app isn't trending.
        if week1 < PRIOR_WEEK_INSTALL_THRESHOLD:
            return 0.0

        score = 0.0
        if week3 > 1.0:
            score = (week1 - week3) / week3
        if score < 0.0:
            score = 0.0
        return score

    # Global trending score.
    week1 = res['aggregations']['week1']['total_installs']['value']
    week3 = res['aggregations']['week3']['total_installs']['value'] / 3.0

    if week1 < PRIOR_WEEK_INSTALL_THRESHOLD:
        # If global installs over the last week aren't over 100, we
        # short-circuit and return a zero-like value as this is not a trending
        # app by definition. Since global installs aren't above 100, per-region
        # installs won't be either.
        return {}

    results = {
        'all': _score(week1, week3)
    }

    if 'region' in res['aggregations']:
        for regional_res in res['aggregations']['region']['buckets']:
            region_slug = regional_res['key']
            week1 = regional_res['week1']['total_installs']['value']
            week3 = regional_res['week3']['total_installs']['value'] / 3.0
            results[region_slug] = _score(week1, week3)

    return results


@cronjobs.register
@use_master
def update_app_trending():
    """
    Update trending for all published apps.

    We break these into chunks so we can bulk index them. Each chunk will
    process the apps in it and reindex them in bulk. After all the chunks are
    processed we find records that haven't been updated and purge/reindex those
    so we nullify their values.

    """
    chunk_size = 100

    ids = list(Webapp.objects.filter(status=mkt.STATUS_PUBLIC,
                                     disabled_by_user=False)
                     .values_list('id', flat=True))

    for chunk in chunked(ids, chunk_size):

        count = 0
        times = []
        reindex_ids = []

        for app in Webapp.objects.filter(id__in=chunk).no_transforms():

            reindex = False
            count += 1
            now = datetime.now()
            t_start = time.time()

            scores = _get_trending(app.id)

            # Update global trending, then per-region trending below.
            value = scores.get('all')
            if value > 0:
                reindex = True
                trending, created = app.trending.get_or_create(
                    region=0, defaults={'value': value})
                if not created:
                    trending.update(value=value, modified=now)
            else:
                # The value is <= 0 so the app is not trending. Let's remove it
                # from the trending table.
                app.trending.filter(region=0).delete()

            for region in mkt.regions.REGIONS_DICT.values():
                value = scores.get(region.slug)
                if value > 0:
                    reindex = True
                    trending, created = app.trending.get_or_create(
                        region=region.id, defaults={'value': value})
                    if not created:
                        trending.update(value=value, modified=now)
                else:
                    # The value is <= 0 so the app is not trending.
                    # Let's remove it from the trending table.
                    app.trending.filter(region=region.id).delete()

            times.append(time.time() - t_start)

            if reindex:
                reindex_ids.append(app.id)

        # Now reindex the apps that actually have a trending score.
        if reindex_ids:
            WebappIndexer.run_indexing(reindex_ids)

        log.info('Trending calculated for %s apps. Avg time overall: '
                 '%0.2fs' % (count, sum(times) / count))

    # Purge any records that were not updated.
    #
    # Note: We force update `modified` even if no data changes so any records
    # with older modified times can be purged.
    now = datetime.now()
    midnight = datetime(year=now.year, month=now.month, day=now.day)

    qs = Trending.objects.filter(modified__lte=midnight)
    # First get the IDs so we know what to reindex.
    purged_ids = qs.values_list('addon', flat=True).distinct()
    # Then delete them.
    qs.delete()

    for ids in chunked(purged_ids, chunk_size):
        WebappIndexer.run_indexing(ids)


@cronjobs.register
def dump_user_installs_cron():
    """
    Sets up tasks to do user install dumps.
    """
    chunk_size = 100
    # Get valid users to dump.
    user_ids = set(Installed.objects.filter(user__enable_recommendations=True)
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


def _remove_stale_files(path, max_age_seconds, msg, storage):
    # Local storage uses local time for file modification. S3 uses UTC time.
    now = datetime.utcnow if storage_is_remote() else datetime.now

    # Look for files (ignore directories) to delete in the path.
    for file_name in storage.listdir(path)[1]:
        file_path = os.path.join(path, file_name)
        age = now() - storage.modified_time(file_path)
        if age.total_seconds() > max_age_seconds:
            log.debug(msg.format(file_path))
            storage.remove(file_path)


@cronjobs.register
def mkt_gc(**kw):
    """Site-wide garbage collections."""
    log.debug('Collecting data to delete')
    logs = (ActivityLog.objects.filter(created__lt=days_ago(90))
            .exclude(action__in=mkt.LOG_KEEP).values_list('id', flat=True))

    for chunk in chunked(logs, 100):
        chunk.sort()
        log.debug('Deleting log entries: %s' % str(chunk))
        delete_logs.delay(chunk)

    # Clear oauth nonce rows. These expire after 10 minutes but we're just
    # clearing those that are more than 1 day old.
    Nonce.objects.filter(created__lt=days_ago(1)).delete()

    # Delete the dump apps over 30 days.
    _remove_stale_files(os.path.join(settings.DUMPED_APPS_PATH, 'tarballs'),
                        settings.DUMPED_APPS_DAYS_DELETE,
                        'Deleting old tarball: {0}',
                        storage=public_storage)

    # Delete the dumped user installs over 30 days.
    _remove_stale_files(os.path.join(settings.DUMPED_USERS_PATH, 'tarballs'),
                        settings.DUMPED_USERS_DAYS_DELETE,
                        'Deleting old tarball: {0}',
                        storage=public_storage)

    # Delete old files in select directories under TMP_PATH.
    _remove_stale_files(os.path.join(settings.TMP_PATH, 'preview'),
                        settings.TMP_PATH_DAYS_DELETE,
                        'Deleting TMP_PATH file: {0}',
                        storage=private_storage)
    _remove_stale_files(os.path.join(settings.TMP_PATH, 'icon'),
                        settings.TMP_PATH_DAYS_DELETE,
                        'Deleting TMP_PATH file: {0}',
                        storage=private_storage)

    # Delete stale FileUploads.
    for fu in FileUpload.objects.filter(created__lte=days_ago(90)):
        log.debug(u'[FileUpload:{uuid}] Removing file: {path}'
                  .format(uuid=fu.uuid, path=fu.path))
        if fu.path:
            try:
                private_storage.remove(fu.path)
            except OSError:
                pass
        fu.delete()
