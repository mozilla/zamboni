import logging
import sys

from django.conf import settings

from elasticutils.contrib.django import Indexable, MappingType

import amo
from amo.decorators import write
from lib.es.models import Reindexing
from lib.post_request_task.task import task as post_request_task
from mkt.search.utils import S


task_log = logging.getLogger('z.task')


class BaseIndexer(MappingType, Indexable):
    """
    A class inheriting from BaseIndexer should implement:

    - get_model(cls)
    - get_mapping(cls)
    - extract_document(cls, obj_id, obj=None)
    """

    @classmethod
    def get_index(cls):
        return settings.ES_INDEXES[cls.get_mapping_type_name()]

    @classmethod
    def get_mapping_type_name(cls):
        return cls.get_model()._meta.db_table

    @classmethod
    def search(cls):
        """
        Returns an elasticutils `S` object to start chaining search methods on.
        """
        return S(cls)

    @classmethod
    def get_settings(cls, settings_override=None):
        """
        Returns settings to be passed to ES create_index.

        If `settings_override` is provided, this will use `settings_override`
        to override the defaults defined here.

        """
        default_settings = {
            'number_of_replicas': settings.ES_DEFAULT_NUM_REPLICAS,
            'number_of_shards': settings.ES_DEFAULT_NUM_SHARDS,
            'refresh_interval': '5s',
            'store.compress.tv': True,
            'store.compress.stored': True,
            'analysis': cls.get_analysis(),
        }
        if settings_override:
            default_settings.update(settings_override)

        return default_settings

    @classmethod
    def get_analysis(cls):
        """
        Returns the analysis dict to be used in settings for create_index.

        For languages that ES supports we define either the minimal or light
        stemming, which isn't as aggresive as the snowball stemmer. We also
        define the stopwords for that language.

        For all languages we've customized we're using the ICU plugin.

        """
        filters = {}
        analyzers = {}

        # Customize the word_delimiter filter to set various options.
        filters['custom_word_delimiter'] = {
            'type': 'word_delimiter',
            'preserve_original': True,
        }

        # The default is used for fields that need ICU but are composed of
        # many languages.
        analyzers['default_icu'] = {
            'type': 'custom',
            'tokenizer': 'icu_tokenizer',
            'filter': ['custom_word_delimiter', 'icu_folding',
                       'icu_normalizer'],
        }

        for lang, stemmer in amo.STEMMER_MAP.items():
            filters['%s_stem_filter' % lang] = {
                'type': 'stemmer',
                'name': stemmer,
            }
            filters['%s_stop_filter' % lang] = {
                'type': 'stop',
                'stopwords': ['_%s_' % lang],
            }

            analyzers['%s_analyzer' % lang] = {
                'type': 'custom',
                'tokenizer': 'icu_tokenizer',
                'filter': [
                    'custom_word_delimiter', 'icu_folding', 'icu_normalizer',
                    '%s_stop_filter' % lang, '%s_stem_filter' % lang
                ],
            }

        return {
            'analyzer': analyzers,
            'filter': filters,
        }

    @classmethod
    def setup_mapping(cls):
        """Creates the ES index/mapping."""
        cls.get_es().create_index(cls.get_index(),
                                  {'mappings': cls.get_mapping(),
                                   'settings': cls.get_settings()})

    @classmethod
    def get_indexable(cls):
        return cls.get_model().objects.order_by('-id')

    @classmethod
    def run_indexing(cls, ids, ES, index=None, **kw):
        """Used in reindex_mkt."""
        sys.stdout.write('Indexing {0} {1}\n'.format(
            len(ids), cls.get_model()._meta.model_name))

        # Fetch QS given the IDs.
        docs = []
        qs = cls.get_model().objects.filter(id__in=ids)

        # For each object, extract document.
        for obj in qs:
            try:
                docs.append(cls.extract_document(obj.id, obj=obj))
            except Exception as e:
                sys.stdout.write('Failed to index {0} {1}: {2}\n'.format(
                    cls.get_model()._meta.model_name, obj.id, e))

        # Index.
        cls.bulk_index(docs, es=ES, index=index or cls.get_index())


@post_request_task(acks_late=True)
@write
def index(ids, indexer, **kw):
    """
    Given a list of IDs and an indexer, index into ES.
    If an reindexation is currently occurring, index on both the old and new.
    """
    task_log.info('Indexing {0} {1}-{2}. [{3}]'.format(
        indexer.get_model()._meta.model_name, ids[0], ids[-1], len(ids)))

    # If reindexing is currently occurring, index on both old and new indexes.
    indices = Reindexing.get_indices(indexer.get_index())

    es = indexer.get_es(urls=settings.ES_URLS)
    for obj in indexer.get_indexable().filter(id__in=ids):
        doc = indexer.extract_document(obj.id, obj)
        for idx in indices:
            indexer.index(doc, id_=obj.id, es=es, index=idx)
