import logging
import sys

from django.conf import settings

import elasticsearch
from celeryutils import task
from elasticsearch import helpers
from elasticsearch_dsl import Search

import amo
from amo.decorators import write
from lib.es.models import Reindexing
from lib.post_request_task.task import task as post_request_task


task_log = logging.getLogger('z.task')


class BaseIndexer(object):
    """
    A class inheriting from BaseIndexer should implement:

    - get_model(cls)
    - get_mapping(cls)
    - extract_document(cls, pk=None, obj=None)

    """
    _es = {}

    @classmethod
    def _key(cls, es_settings):
        """
        Create a hashed key based on settings.

        This allows us to cache Elasticsearch objects based on settings.

        """
        es_settings = sorted(es_settings.items(), key=lambda item: item[0])
        es_settings = repr([(k, v) for k, v in es_settings])
        return tuple(es_settings)

    @classmethod
    def get_es(cls, **overrides):
        """
        Returns an Elasticsearch object using Django settings.

        We override elasticutil's `get_es` because we're using the official
        elasticsearch client library.

        """
        defaults = {
            'hosts': settings.ES_HOSTS,
            'timeout': getattr(settings, 'ES_TIMEOUT', 10),
        }
        defaults.update(overrides)

        key = cls._key(defaults)
        if key in cls._es:
            return cls._es[key]

        es = elasticsearch.Elasticsearch(**defaults)
        cls._es[key] = es
        return es

    @classmethod
    def index(cls, document, id_=None, es=None, index=None):
        """Index one document."""
        es = es or cls.get_es()
        index = index or cls.get_index()
        es.index(index=index, doc_type=cls.get_mapping_type_name(),
                 body=document, id=id_)

    @classmethod
    def bulk_index(cls, documents, id_field='id', es=None, index=None):
        """Index of a bunch of documents."""
        es = es or cls.get_es()
        index = index or cls.get_index()
        type = cls.get_mapping_type_name()

        actions = [
            {'_index': index, '_type': type, '_id': d['id'], '_source': d}
            for d in documents]

        helpers.bulk(es, actions)

    @classmethod
    def index_ids(cls, ids, no_delay=False):
        """
        Start task to index instances of indexer class matching the IDs.
        Calls the helper method outside this BaseIndexer class.
        """
        if no_delay:
            index(ids, cls)
        else:
            index.delay(ids, cls)

    @classmethod
    def unindex(cls, id_, es=None, index=None):
        """
        Remove a document from the index.
        """
        es = es or cls.get_es()
        index = index or cls.get_index()
        es.delete(index=index, doc_type=cls.get_mapping_type_name(), id=id_)

    @classmethod
    def refresh_index(cls, es=None, index=None):
        """
        Refresh the index.
        """
        es = es or cls.get_es()
        index = index or cls.get_index()
        es.indices.refresh(index=index)

    @classmethod
    def search(cls, using=None):
        """
        Returns a `Search` object from elasticsearch_dsl.
        """
        return Search(using=using or cls.get_es(),
                      index=cls.get_index(),
                      doc_type=cls.get_mapping_type_name())

    @classmethod
    def get_index(cls):
        return settings.ES_INDEXES[cls.get_mapping_type_name()]

    @classmethod
    def get_mapping_type_name(cls):
        return cls.get_model()._meta.db_table

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
    def get_not_analyzed(cls):
        """Returns {'type': 'string', 'index': 'not_analyzed'} as shorthand."""
        return {'type': 'string', 'index': 'not_analyzed'}

    @classmethod
    def setup_mapping(cls):
        """Creates the ES index/mapping."""
        cls.get_es().indices.create(
            index=cls.get_index(), body={'mappings': cls.get_mapping(),
                                         'settings': cls.get_settings()})

    @classmethod
    def get_indexable(cls):
        """Returns base queryset that is able to be indexed."""
        return cls.get_model().objects.order_by('-id')

    @classmethod
    @task
    def unindexer(cls, ids=None, _all=False, index=None):
        """
        Empties an index, but doesn't delete it. Useful for tearDowns.

        ids -- list of IDs to unindex.
        _all -- unindex all objects.
        """
        if _all:
            # Mostly used for test tearDowns.
            qs = cls.get_model()
            if hasattr(qs, 'with_deleted'):
                qs = qs.with_deleted
            else:
                qs = qs.objects
            ids = list(qs.order_by('id').values_list('id', flat=True))
        if not ids:
            return

        task_log.info('Unindexing %s %s-%s. [%s]' %
                      (cls.get_model()._meta.model_name, ids[0], ids[-1],
                       len(ids)))

        index = index or cls.get_index()
        # Note: If reindexing is currently occurring, `get_indices` will return
        # more than one index.
        indices = Reindexing.get_indices(index)

        es = cls.get_es(urls=settings.ES_URLS)
        for id_ in ids:
            for idx in indices:
                try:
                    cls.unindex(id_=id_, es=es, index=idx)
                except elasticsearch.exceptions.NotFoundError:
                    # Ignore if it's not there.
                    task_log.info(u'[%s:%s] object not found in index' %
                                  (cls.get_model()._meta.model_name, id_))

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
        if docs:
            cls.bulk_index(docs, es=ES, index=index or cls.get_index())

    @classmethod
    def attach_translation_mappings(cls, mapping, field_names):
        """
        For each field in field name, attach a mapping property to the ES
        mapping that appends "_translations" to the key, and has type string
        that is not_analyzed.
        """
        for field_name in field_names:
            # _translations is the suffix in TranslationSerializer.
            mapping[cls.get_mapping_type_name()]['properties'].update({
                '%s_translations' % field_name: {
                    'type': 'object',
                    'properties': {
                        'lang': {'type': 'string',
                                 'index': 'not_analyzed'},
                        'string': {'type': 'string',
                                   'index': 'not_analyzed'},
                    }
                }
            })
        return mapping


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
