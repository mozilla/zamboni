from datetime import date, timedelta
import itertools

from django.db import transaction

import commonware.log
from celery.task.sets import TaskSet
from celeryutils import task

import amo
import cronjobs
from amo.utils import chunked, slugify
from bandwagon.models import Collection, SyncedCollection


task_log = commonware.log.getLogger('z.task')


# TODO: remove this once zamboni enforces slugs.
@cronjobs.register
def collections_add_slugs():
    """Give slugs to any slugless collections."""
    # Don't touch the modified date.
    Collection._meta.get_field('modified').auto_now = False
    q = Collection.objects.filter(slug=None)
    ids = q.values_list('id', flat=True)
    task_log.info('%s collections without names' % len(ids))
    max_length = Collection._meta.get_field('slug').max_length
    cnt = itertools.count()
    # Chunk it so we don't do huge queries.
    for chunk in chunked(ids, 300):
        for c in q.no_cache().filter(id__in=chunk):
            c.slug = c.nickname or slugify(c.name)[:max_length]
            if not c.slug:
                c.slug = 'collection'
            c.save(force_update=True)
            task_log.info(u'%s. %s => %s' % (next(cnt), c.name, c.slug))


@cronjobs.register
def cleanup_synced_collections():
    _cleanup_synced_collections.delay()


@task(rate_limit='1/m')
@transaction.commit_on_success
def _cleanup_synced_collections(**kw):
    task_log.info("[300@%s] Dropping synced collections." %
                   _cleanup_synced_collections.rate_limit)

    thirty_days = date.today() - timedelta(days=30)
    ids = (SyncedCollection.objects.filter(created__lte=thirty_days)
           .values_list('id', flat=True))[:300]

    for chunk in chunked(ids, 100):
        SyncedCollection.objects.filter(id__in=chunk).delete()

    if ids:
        _cleanup_synced_collections.delay()


@cronjobs.register
def drop_collection_recs():
    _drop_collection_recs.delay()


@task(rate_limit='1/m')
@transaction.commit_on_success
def _drop_collection_recs(**kw):
    task_log.info("[300@%s] Dropping recommended collections." %
                   _drop_collection_recs.rate_limit)
    # Get the first 300 collections and delete them in smaller chunks.
    types = amo.COLLECTION_SYNCHRONIZED, amo.COLLECTION_RECOMMENDED
    ids = (Collection.objects.filter(type__in=types, author__isnull=True)
           .values_list('id', flat=True))[:300]

    for chunk in chunked(ids, 100):
        Collection.objects.filter(id__in=chunk).delete()

    # Go again if we found something to delete.
    if ids:
        _drop_collection_recs.delay()
