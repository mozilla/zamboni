"""
Marketplace ElasticSearch Indexer.

Currently creates the indexes and re-indexes apps and feed elements.
"""
import itertools
import logging
import sys
import time
from math import ceil
from optparse import make_option

import elasticsearch
from celery import chain, chord, task

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

import mkt.feed.indexers as f_indexers
from lib.es.models import Reindexing
from mkt.extensions.indexers import ExtensionIndexer
from mkt.site.utils import chunked, timestamp_index
from mkt.webapps.indexers import WebappIndexer
from mkt.websites.indexers import WebsiteIndexer


logger = logging.getLogger('z.elasticsearch')


# Enable these to get full debugging information.
# logging.getLogger('elasticsearch').setLevel(logging.DEBUG)
# logging.getLogger('elasticsearch.trace').setLevel(logging.DEBUG)

# The subset of settings.ES_INDEXES we are concerned with.
ES_INDEXES = settings.ES_INDEXES

# When `--index=...` is provided to the management command, we index the
# following subsets.
INDEX_CHOICES = {
    # In case we want to index only a subset of indexes.
    'apps': [WebappIndexer],
    'extensions': [ExtensionIndexer],
    'feed': [f_indexers.FeedAppIndexer,
             f_indexers.FeedBrandIndexer,
             f_indexers.FeedCollectionIndexer,
             f_indexers.FeedShelfIndexer,
             f_indexers.FeedItemIndexer],
    'feeditems': [f_indexers.FeedItemIndexer],
    'websites': [WebsiteIndexer],

}

# Get the list of all possible distinct indexers from INDEX_CHOICES.
INDEXERS = list(set(itertools.chain.from_iterable(INDEX_CHOICES.values())))

# We have this mapping so we can pass which indexer to use to celery.
INDEXER_MAP = dict((indexer.get_mapping_type_name(), indexer)
                   for indexer in INDEXERS)

ES = elasticsearch.Elasticsearch(hosts=settings.ES_HOSTS)


def _print(msg, alias=''):
    prepend = ''
    if alias:
        prepend = '[alias:{alias}] '.format(alias=alias)
    msg = '\n{prepend}{msg}'.format(prepend=prepend, msg=msg)
    sys.stdout.write(msg)


@task
def pre_index(new_index, old_index, alias, index_name, settings):
    """
    This sets up everything needed before indexing:
        * Flags the database.
        * Creates the new index.

    """
    indexer = INDEXER_MAP[index_name]

    # Flag the database to indicate that the reindexing has started.
    _print('Flagging the database to start the reindexation.', alias)
    Reindexing.flag_reindexing(new_index=new_index, old_index=old_index,
                               alias=alias)
    time.sleep(5)  # Give the celery worker some time to flag the DB.

    _print('Creating the mapping for index {index}.'.format(index=new_index),
           alias)

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


@task
def post_index(new_index, old_index, alias, index_name, settings):
    """
    Perform post-indexing tasks:
        * Optimize (which also does a refresh and a flush by default).
        * Update settings to reset number of replicas.
        * Point the alias to this new index.
        * Unflag the database.
        * Remove the old index.
        * Output the current alias configuration.

    """
    _print('Optimizing, updating settings and aliases.', alias)

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

    _print('Unflagging the database.', alias)
    Reindexing.unflag_reindexing(alias=alias)

    _print('Removing index {index}.'.format(index=old_index), alias)
    if old_index and ES.indices.exists(index=old_index):
        ES.indices.delete(index=old_index)

    alias_output = ''
    for indexer in INDEXERS:
        alias = ES_INDEXES[indexer.get_mapping_type_name()]
        alias_output += unicode(ES.indices.get_aliases(index=alias)) + '\n'

    _print('Reindexation done. Current aliases configuration: '
           '{output}\n'.format(output=alias_output), alias)


@task(ignore_result=False)
def run_indexing(index, index_name, ids):
    """Index the objects.

    - index: name of the index

    Note: `ignore_result=False` is required for the chord to work and trigger
    the callback.

    """
    indexer = INDEXER_MAP[index_name]
    indexer.run_indexing(ids, ES, index=index)


def chunk_indexing(indexer, chunk_size):
    """Chunk the items to index."""
    chunks = list(indexer.get_indexable().values_list('id', flat=True))
    return chunked(chunks, chunk_size), len(chunks)


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
        index_choice = kwargs.get('index', None)
        prefix = kwargs.get('prefix', '')
        force = kwargs.get('force', False)

        if index_choice:
            # If we only want to reindex a subset of indexes.
            INDEXES = INDEX_CHOICES.get(index_choice, None)
            if INDEXES is None:
                raise CommandError(
                    'Incorrect index name specified. '
                    'Choose one of: %s' % ', '.join(INDEX_CHOICES.keys()))
        else:
            INDEXES = INDEXERS

        if Reindexing.is_reindexing() and not force:
            raise CommandError('Indexation already occuring - use --force to '
                               'bypass')
        elif force:
            Reindexing.unflag_reindexing()

        for INDEXER in INDEXES:
            index_name = INDEXER.get_mapping_type_name()
            chunk_size = INDEXER.chunk_size
            alias = ES_INDEXES[index_name]

            chunks, total = chunk_indexing(INDEXER, chunk_size)
            if not total:
                _print('No items to queue.', alias)
            else:
                total_chunks = int(ceil(total / float(chunk_size)))
                _print('Indexing {total} items into {n} chunks of size {size}'
                       .format(total=total, n=total_chunks, size=chunk_size),
                       alias)

            # Get the old index if it exists.
            try:
                aliases = ES.indices.get_alias(name=alias).keys()
            except elasticsearch.NotFoundError:
                aliases = []
            old_index = aliases[0] if aliases else None

            # Create a new index, using the index name with a timestamp.
            new_index = timestamp_index(prefix + alias)

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

            pre_task = pre_index.si(new_index, old_index, alias, index_name, {
                'analysis': INDEXER.get_analysis(),
                'number_of_replicas': 0,
                'number_of_shards': num_shards,
                'store.compress.tv': True,
                'store.compress.stored': True,
                'refresh_interval': '-1'})
            post_task = post_index.si(new_index, old_index, alias, index_name,
                                      {'number_of_replicas': num_replicas,
                                       'refresh_interval': '5s'})

            # Ship it.
            if not total:
                # If there's no data we still create the index and alias.
                chain(pre_task, post_task).apply_async()
            else:
                index_tasks = [run_indexing.si(new_index, index_name, chunk)
                               for chunk in chunks]

                if settings.CELERY_ALWAYS_EAGER:
                    # Eager mode and chords don't get along. So we serialize
                    # the tasks as a workaround.
                    index_tasks.insert(0, pre_task)
                    index_tasks.append(post_task)
                    chain(*index_tasks).apply_async()
                else:
                    chain(pre_task, chord(header=index_tasks,
                                          body=post_task)).apply_async()

        _print('New index and indexing tasks all queued up.')
