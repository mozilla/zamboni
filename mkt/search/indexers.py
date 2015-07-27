import logging
import sys

from django.conf import settings

import elasticsearch
from celery import task
from elasticsearch import helpers
from elasticsearch_dsl import Search

import mkt
from lib.es.models import Reindexing
from lib.post_request_task.task import task as post_request_task
from mkt.constants.regions import MATURE_REGION_IDS
from mkt.search.utils import get_boost
from mkt.site.decorators import use_master
from mkt.translations.utils import to_language


log = logging.getLogger('z.task')


class BaseIndexer(object):
    """
    A class inheriting from BaseIndexer should implement:

    - get_model(cls)
    - get_mapping(cls)
    - extract_document(cls, pk=None, obj=None)

    """
    _es = {}

    """Fields we don't need to expose in the results, only used for filtering
    or sorting."""
    hidden_fields = ()

    # How many documents do we use when bulk indexing. The goal is to send
    # about 2.5mb of data to Elasticsearch during bulk indexing.
    chunk_size = 500

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
        return (Search(
            using=using or cls.get_es(),
            index=cls.get_index(),
            doc_type=cls.get_mapping_type_name())
            .extra(_source={'exclude': cls.hidden_fields}))

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
                       'icu_normalizer', 'lowercase'],
        }

        # An analyzer that can do case-insensitive exact matching.
        analyzers['exact_lowercase'] = {
            'type': 'custom',
            'tokenizer': 'keyword',
            'filter': ['lowercase'],
        }

        for lang, stemmer in mkt.STEMMER_MAP.items():
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
                    '%s_stop_filter' % lang, '%s_stem_filter' % lang,
                    'lowercase',
                ],
            }

        return {
            'analyzer': analyzers,
            'filter': filters,
        }

    @classmethod
    def string_not_analyzed(cls, **kwargs):
        """Shorthand for a non-analyzed string."""
        default = {'type': 'string', 'index': 'not_analyzed'}
        if kwargs:
            default.update(kwargs)
        return default

    @classmethod
    def string_not_indexed(cls, **kwargs):
        """Shorthand for a non-indexed string."""
        default = {'type': 'string', 'index': 'no'}
        if kwargs:
            default.update(kwargs)
        return default

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

        log.info('Unindexing %s %s-%s. [%s]' %
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
                    log.info(u'[%s:%s] object not found in index' %
                             (cls.get_model()._meta.model_name, id_))

    @classmethod
    def run_indexing(cls, ids, ES, index=None, **kw):
        """Used in reindex."""
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
    def attach_boost_mapping(cls, mapping):
        """
        Add a boost field to the mapping to enhance relevancy of a document.
        This is used by SearchQueryFilter in a function scoring query.
        """
        mapping[cls.get_mapping_type_name()]['properties']['boost'] = {
            'type': 'float', 'doc_values': True
        }
        return mapping

    @classmethod
    def attach_translation_mappings(cls, mapping, field_names):
        """
        For each field in field_names, attach a dict to the ES mapping
        properties making "<field_name>_translations" an object containing
        "string" and "lang" as non-indexed strings.

        Used to store non-indexed, non-analyzed translations in ES that will be
        sent back by the API for each item. It does not take care of the
        indexed content for search, it's there only to store and return
        raw translations.
        """
        for field_name in field_names:
            # _translations is the suffix in TranslationSerializer.
            mapping[cls.get_mapping_type_name()]['properties'].update({
                '%s_translations' % field_name: {
                    'type': 'object',
                    'properties': {
                        'lang': cls.string_not_indexed(),
                        'string': cls.string_not_indexed(),
                    }
                }
            })
        return mapping

    @classmethod
    def attach_language_specific_analyzers(cls, mapping, field_names):
        """
        For each field in field_names, attach language-specific mappings that
        will use specific analyzers for these fields in every language that we
        support.

        These mappings are used by the search filtering code if they exist.
        """
        def _locale_field_mapping(field, analyzer):
            return {
                '%s_l10n_%s' % (field, analyzer): {
                    'type': 'string',
                    'analyzer': (('%s_analyzer' % analyzer)
                                 if analyzer in mkt.STEMMER_MAP else analyzer)
                }
            }

        doc_type = cls.get_mapping_type_name()

        for analyzer in mkt.SEARCH_ANALYZER_MAP:
            if (not settings.ES_USE_PLUGINS and
                    analyzer in mkt.SEARCH_ANALYZER_PLUGINS):
                # Skip analyzers that need special plugins if the use of
                # plugins is disabled in settings.
                log.info('While creating mapping, skipping the %s analyzer'
                         % analyzer)
                continue

            for field in field_names:
                mapping[doc_type]['properties'].update(
                    _locale_field_mapping(field, analyzer))

            return mapping

    @classmethod
    def attach_trending_and_popularity_mappings(cls, mapping):
        doc_type = cls.get_mapping_type_name()
        new_properties = {}

        # Add global popularity and trending fields.
        new_properties['popularity'] = {
            'type': 'long', 'doc_values': True
        }
        new_properties['trending'] = {
            'type': 'long', 'doc_values': True
        }
        # Add region-specific popularity / trending fields for mature regions.
        # We don't have to store anything for adolescent regions, as the
        # sorting code in SortingFilter will not try to sort using the regional
        # value if the region in the request is adolescent.
        for region in MATURE_REGION_IDS:
            new_properties['popularity_%s' % region] = {
                'type': 'long', 'doc_values': True
            }
            new_properties['trending_%s' % region] = {
                'type': 'long', 'doc_values': True
            }
        # Add everything to the mapping.
        mapping[doc_type]['properties'].update(new_properties)
        return mapping

    @classmethod
    def extract_popularity_trending_boost(cls, obj):
        # 0 is a special region when considering popularity/trending, it's the
        # one holding the global value.
        ALL_REGIONS_ID = 0

        def get_dict(obj, prop):
            if obj.is_dummy_content_for_qa():
                return {}
            qs = getattr(obj, prop).filter(
                region__in=MATURE_REGION_IDS + [ALL_REGIONS_ID])
            return dict(qs.values_list('region', 'value'))

        extend = {
            'boost': get_boost(obj),
        }
        trending = get_dict(obj, 'trending')
        popularity = get_dict(obj, 'popularity')

        # Global popularity.
        extend['trending'] = trending.get(ALL_REGIONS_ID, 0)
        extend['popularity'] = popularity.get(ALL_REGIONS_ID, 0)

        # For all mature regions, store in ES the value from the queries we
        # made, or 0 if none was found. As in the
        # attach_trending_and_popularity_mappings() method above, no neeed to
        # store anything for the adolescent regions.
        for region_id in MATURE_REGION_IDS:
            extend['trending_%s' % region_id] = trending.get(region_id, 0)
            extend['popularity_%s' % region_id] = popularity.get(region_id, 0)

        return extend

    @classmethod
    def extract_field_translations(cls, obj, field, db_field=None,
                                   include_field_for_search=False):
        """
        Returns a dict with:
        - A special list (with _translations key suffix) mapping languages to
          translations, to be deserialized by ESTranslationSerializerField.
        - A list with all translations, intended to be analyzed and used for
          searching (only included if include_field_for_search is True,
          defaults to False).
        """
        if db_field is None:
            db_field = '%s_id' % field

        extend_with_me = {
            '%s_translations' % field: [
                {'lang': to_language(lang), 'string': string}
                for lang, string in obj.translations[getattr(obj, db_field)]
                if string
            ]
        }
        if include_field_for_search:
            extend_with_me[field] = list(
                set(s for _, s in obj.translations[getattr(obj, db_field)])
            )
        return extend_with_me

    @classmethod
    def extract_field_analyzed_translations(cls, obj, field, db_field=None):
        """
        Returns a dict containing translations for each language-specific
        analyzer for the given field.
        """
        if db_field is None:
            db_field = '%s_id' % field

        extend_with_me = {}

        # Indices for each language. languages is a list of locales we want to
        # index with analyzer if the string's locale matches.
        for analyzer, languages in mkt.SEARCH_ANALYZER_MAP.iteritems():
            if (not settings.ES_USE_PLUGINS and
                    analyzer in mkt.SEARCH_ANALYZER_PLUGINS):
                continue

            extend_with_me['%s_l10n_%s' % (field, analyzer)] = list(
                set(string for locale, string
                    in obj.translations[getattr(obj, db_field)]
                    if locale.lower() in languages))

        return extend_with_me


@post_request_task(acks_late=True)
@use_master
def index(ids, indexer, **kw):
    """
    Given a list of IDs and an indexer, index into ES.
    If an reindexation is currently occurring, index on both the old and new.
    """
    log.info('Indexing {0} {1}-{2}. [{3}]'.format(
        indexer.get_model()._meta.model_name, ids[0], ids[-1], len(ids)))

    # If reindexing is currently occurring, index on both old and new indexes.
    indices = Reindexing.get_indices(indexer.get_index())

    es = indexer.get_es(urls=settings.ES_URLS)
    for obj in indexer.get_indexable().filter(id__in=ids):
        doc = indexer.extract_document(obj.id, obj)
        for idx in indices:
            indexer.index(doc, id_=obj.id, es=es, index=idx)
