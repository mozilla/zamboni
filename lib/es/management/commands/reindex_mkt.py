"""
Marketplace ElasticSearch Indexer.

Currently indexes apps and feed elements.
"""
import logging
import os
import sys
import time
from optparse import make_option

import pyelasticsearch
from celery import task

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from amo.utils import chunked, timestamp_index
from lib.es.models import Reindexing

from mkt.feed.indexers import (FeedAppIndexer, FeedBrandIndexer,
                               FeedCollectionIndexer)
from mkt.webapps.models import WebappIndexer


logger = logging.getLogger('z.elasticsearch')


# Enable these to get full debugging information.
# logging.getLogger('pyelasticsearch').setLevel(logging.DEBUG)
# logging.getLogger('requests').setLevel(logging.DEBUG)


# The subset of settings.ES_INDEXES we are concerned with.
INDEXES = (
    (settings.ES_INDEXES['webapp'], WebappIndexer),
    (settings.ES_INDEXES['mkt_feed_app'], FeedAppIndexer),
    (settings.ES_INDEXES['mkt_feed_brand'], FeedBrandIndexer),
    (settings.ES_INDEXES['mkt_feed_collection'], FeedCollectionIndexer),
)

if hasattr(settings, 'ES_URLS'):
    ES_URL = settings.ES_URLS[0]
else:
    ES_URL = 'http://127.0.0.1:9200'


ES = pyelasticsearch.ElasticSearch(ES_URL)


job = 'lib.es.management.commands.reindex_mkt.run_indexing'
time_limits = settings.CELERY_TIME_LIMITS[job]


@task
def delete_index(old_index):
    """Removes the index."""
    sys.stdout.write('Removing index %r' % old_index)
    ES.delete_index(old_index)


@task
def create_index(new_index, alias, indexer, settings):
    """Creates a mapping for the new index.

    - new_index: new index name
    - alias: alias name
    - settings: a dictionary of settings

    """
    sys.stdout.write(
        'Create the mapping for index %r, alias: %r' % (new_index, alias))

    # Update settings with mapping.
    settings = {
        'settings': settings,
        'mappings': indexer.get_mapping(),
    }

    # Create index and mapping.
    try:
        ES.create_index(new_index, settings)
    except pyelasticsearch.exceptions.IndexAlreadyExistsError:
        raise CommandError('New index [%s] already exists' % new_index)

    # Don't return until the health is green. By default waits for 30s.
    ES.health(new_index, wait_for_status='green', wait_for_relocating_shards=0)


@task(time_limit=time_limits['hard'], soft_time_limit=time_limits['soft'])
def run_indexing(index, indexer):
    """Index the objects.

    - index: name of the index

    Note: Our ES doc sizes are about 5k in size. Chunking by 100 sends ~500kb
    of data to ES at a time.

    TODO: Use celery chords here to parallelize these indexing chunks. This
          requires celery 3 (bug 825938).

    """
    sys.stdout.write('Indexing apps into index: %s' % index)

    qs = indexer.get_indexable()
    for ids in chunked(list(qs), 100):
        indexer.run_indexing(ids, ES, index=index)


@task
def flag_database(new_index, old_index, alias):
    """Flags the database to indicate that the reindexing has started."""
    sys.stdout.write('Flagging the database to start the reindexation')
    Reindexing.flag_reindexing(new_index=new_index, old_index=old_index,
                               alias=alias)
    time.sleep(5)  # Give celeryd some time to flag the DB.


@task
def unflag_database():
    """Unflag the database to indicate that the reindexing is over."""
    sys.stdout.write('Unflagging the database')
    Reindexing.unflag_reindexing()


@task
def update_alias(new_index, old_index, alias, settings):
    """
    Update the alias now that indexing is over.

    We do 3 things:

        1. Optimize (which also does a refresh and a flush by default).
        2. Update settings to reset number of replicas.
        3. Point the alias to this new index.

    """
    sys.stdout.write('Optimizing, updating settings and aliases.')

    # Optimize.
    ES.optimize(new_index)

    # Update the replicas.
    ES.update_settings(new_index, settings)

    # Add and remove aliases.
    actions = [
        {'add': {'index': new_index, 'alias': alias}}
    ]
    if old_index:
        actions.append(
            {'remove': {'index': old_index, 'alias': alias}}
        )
    ES.update_aliases(dict(actions=actions))


@task
def output_summary():
    alias_output = ''
    for ALIAS, INDEXER in INDEXES:
        alias_output += ES.aliases(ALIAS) + '\n'
    sys.stdout.write(
        'Reindexation done. Current Aliases configuration: %s\n' %
        alias_output)


class Command(BaseCommand):
    help = 'Reindex all ES indexes'
    option_list = BaseCommand.option_list + (
        make_option('--prefix', action='store',
                    help='Indexes prefixes, like test_',
                    default=''),
        make_option('--force', action='store_true',
                    help=('Bypass the database flag that says '
                          'another indexation is ongoing'),
                    default=False),
    )

    def handle(self, *args, **kwargs):
        """Set up reindexing tasks.

        Creates a Tasktree that creates a new indexes and indexes all objects,
        then points the alias to this new index when finished.
        """
        force = kwargs.get('force', False)
        prefix = kwargs.get('prefix', '')

        if Reindexing.is_reindexing() and not force:
            raise CommandError('Indexation already occuring - use --force to '
                               'bypass')
        elif force:
            unflag_database()

        chain = None
        old_indexes = []
        for ALIAS, INDEXER in INDEXES:
            # Get the old index if it exists.
            try:
                aliases = ES.aliases(ALIAS).keys()
            except pyelasticsearch.exceptions.ElasticHttpNotFoundError:
                aliases = []
            old_index = aliases[0] if aliases else None
            old_indexes.append(old_index)

            # Create a new index, using the index name with a timestamp.
            new_index = timestamp_index(prefix + ALIAS)

            # See how the index is currently configured.
            if old_index:
                try:
                    s = (ES.get_settings(old_index).get(old_index, {})
                                                   .get('settings', {}))
                except pyelasticsearch.exceptions.ElasticHttpNotFoundError:
                    s = {}
            else:
                s = {}
            num_replicas = s.get('number_of_replicas',
                                 settings.ES_DEFAULT_NUM_REPLICAS)
            num_shards = s.get('number_of_shards',
                               settings.ES_DEFAULT_NUM_SHARDS)

            # Flag the database to mark as currently indexing.
            if not chain:
                chain = flag_database.si(new_index, old_index, ALIAS)
            else:
                chain |= flag_database.si(new_index, old_index, ALIAS)

            # Create the indexes and mappings.
            # Note: We set num_replicas=0 here to lower load while re-indexing.
            # In later step we increase it which results in more efficient bulk
            # copy in ES. For ES < 0.90 we manually enable compression.
            chain |= create_index.si(new_index, ALIAS, INDEXER, {
                'analysis': INDEXER.get_analysis(),
                'number_of_replicas': 0, 'number_of_shards': num_shards,
                'store.compress.tv': True, 'store.compress.stored': True,
                'refresh_interval': '-1'})

            # Index all the things!
            chain |= run_indexing.si(new_index, INDEXER)

            # After indexing we optimize the index, adjust settings, and point
            # alias to the new index.
            chain |= update_alias.si(new_index, old_index, ALIAS, {
                'number_of_replicas': num_replicas, 'refresh_interval': '5s'})

        # Unflag the database to mark as done indexing.
        chain |= unflag_database.si()

        # Delete the old index, if any.
        for old_index in old_indexes:
            if old_index:
                chain |= delete_index.si(old_index)

        # All done!
        chain |= output_summary.si()

        # Ship it.
        self.stdout.write('\nNew index and indexing tasks all queued up.\n')
        os.environ['FORCE_INDEXING'] = '1'
        try:
            chain.apply_async()
        finally:
            del os.environ['FORCE_INDEXING']
