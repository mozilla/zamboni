"""
Marketplace ElasticSearch Indexer.

Currently creates the indexes and re-indexes apps and feed elements.
"""
import logging
import os
import sys
import time
from optparse import make_option

import elasticsearch
from celery import task

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

import mkt.feed.indexers as f_indexers
from amo.utils import chunked, timestamp_index
from lib.es.models import Reindexing
from mkt.webapps.indexers import WebappIndexer


logger = logging.getLogger('z.elasticsearch')


# Enable these to get full debugging information.
# logging.getLogger('elasticsearch').setLevel(logging.DEBUG)
# logging.getLogger('elasticsearch.trace').setLevel(logging.DEBUG)

# The subset of settings.ES_INDEXES we are concerned with.
# Referenced from amo.tests.ESTestCase so update that if you are modifying the
# structure of INDEXES.
ES_INDEXES = settings.ES_INDEXES
INDEXES = (
    # Index, Indexer, chunk size.
    (ES_INDEXES['webapp'], WebappIndexer, 100),
    # Currently using 500 since these are manually created by a curator and
    # there will probably never be this many.
    (ES_INDEXES['mkt_feed_app'], f_indexers.FeedAppIndexer, 500),
    (ES_INDEXES['mkt_feed_brand'], f_indexers.FeedBrandIndexer, 500),
    (ES_INDEXES['mkt_feed_collection'], f_indexers.FeedCollectionIndexer, 500),
    (ES_INDEXES['mkt_feed_shelf'], f_indexers.FeedShelfIndexer, 500),
    # Currently using 1000 since FeedItem documents are pretty small.
    (ES_INDEXES['mkt_feed_item'], f_indexers.FeedItemIndexer, 1000),
)

INDEX_DICT = {
    # In case we want to index only a subset of indexes.
    'apps': [INDEXES[0]],
    'feed': [INDEXES[1], INDEXES[2], INDEXES[3], INDEXES[4], INDEXES[5]],
    'feeditems': [INDEXES[5]],
}

ES = elasticsearch.Elasticsearch(hosts=settings.ES_HOSTS)


job = 'lib.es.management.commands.reindex_mkt.run_indexing'
time_limits = settings.CELERY_TIME_LIMITS[job]


@task
def delete_index(old_index):
    """Removes the index."""
    sys.stdout.write('Removing index %r\n' % old_index)
    ES.indices.delete(index=old_index)


@task
def create_index(new_index, alias, indexer, settings):
    """Creates a mapping for the new index.

    - new_index: new index name
    - alias: alias name
    - settings: a dictionary of settings

    """
    sys.stdout.write(
        'Create the mapping for index %r, alias: %r\n' % (new_index, alias))

    # Update settings with mapping.
    settings = {
        'settings': settings,
        'mappings': indexer.get_mapping(),
    }

    # Create index and mapping.
    try:
        ES.indices.create(index=new_index, body=settings)
    except elasticsearch.ElasticsearchException as e:
        raise CommandError('ERROR: New index [%s] already exists? %s'
                           % (new_index, e))

    # Don't return until the health is green. By default waits for 30s.
    ES.cluster.health(index=new_index, wait_for_status='green',
                      wait_for_relocating_shards=0)


@task(time_limit=time_limits['hard'], soft_time_limit=time_limits['soft'])
def run_indexing(index, indexer, chunk_size):
    """Index the objects.

    - index: name of the index

    Note: Our ES doc sizes are about 5k in size. Chunking by 100 sends ~500kb
    of data to ES at a time.

    TODO: Use celery chords here to parallelize these indexing chunks. This
          requires celery 3 (bug 825938).

    """
    sys.stdout.write('Indexing apps into index: %s\n' % index)

    qs = indexer.get_indexable().values_list('id', flat=True)
    for ids in chunked(list(qs), chunk_size):
        indexer.run_indexing(ids, ES, index=index)


@task
def flag_database(new_index, old_index, alias):
    """Flags the database to indicate that the reindexing has started."""
    sys.stdout.write('Flagging the database to start the reindexation\n')
    Reindexing.flag_reindexing(new_index=new_index, old_index=old_index,
                               alias=alias)
    time.sleep(5)  # Give celeryd some time to flag the DB.


@task
def unflag_database():
    """Unflag the database to indicate that the reindexing is over."""
    sys.stdout.write('Unflagging the database\n')
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
    sys.stdout.write('Optimizing, updating settings and aliases.\n')

    # Optimize.
    ES.indices.optimize(index=new_index)

    # Update the replicas.
    ES.indices.put_settings(index=new_index, body=settings)

    # Add and remove aliases.
    actions = [
        {'add': {'index': new_index, 'alias': alias}}
    ]
    if old_index:
        actions.append(
            {'remove': {'index': old_index, 'alias': alias}}
        )
    ES.indices.update_aliases(body=dict(actions=actions))


@task
def output_summary():
    alias_output = ''
    for ALIAS, INDEXER, CHUNK_SIZE in INDEXES:
        alias_output += unicode(ES.indices.get_aliases(index=ALIAS)) + '\n'
    sys.stdout.write(
        'Reindexation done. Current Aliases configuration: %s\n' %
        alias_output)


class Command(BaseCommand):
    help = 'Reindex all ES indexes'
    option_list = BaseCommand.option_list + (
        make_option('--index', action='store',
                    help='Which indexes to reindex',
                    default=None),
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
        global INDEXES

        index_choice = kwargs.get('index', None)
        prefix = kwargs.get('prefix', '')
        force = kwargs.get('force', False)

        if index_choice:
            # If we only want to reindex a subset of indexes.
            INDEXES = INDEX_DICT.get(index_choice, INDEXES)

        if Reindexing.is_reindexing() and not force:
            raise CommandError('Indexation already occuring - use --force to '
                               'bypass')
        elif force:
            unflag_database()

        chain = None
        old_indexes = []
        for ALIAS, INDEXER, CHUNK_SIZE in INDEXES:
            # Get the old index if it exists.
            try:
                aliases = ES.indices.get_alias(name=ALIAS).keys()
            except elasticsearch.NotFoundError:
                aliases = []
            old_index = aliases[0] if aliases else None
            old_indexes.append(old_index)

            # Create a new index, using the index name with a timestamp.
            new_index = timestamp_index(prefix + ALIAS)

            # See how the index is currently configured.
            if old_index:
                try:
                    s = (ES.indices.get_settings(index=old_index).get(
                        old_index, {}).get('settings', {}))
                except elasticsearch.NotFoundError:
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
            chain |= run_indexing.si(new_index, INDEXER, CHUNK_SIZE)

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
