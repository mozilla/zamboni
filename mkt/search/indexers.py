from django.conf import settings

from elasticutils.contrib.django import Indexable, MappingType

import amo


class BaseIndexer(MappingType, Indexable):

    @classmethod
    def get_index(cls):
        return settings.ES_INDEXES[cls.get_mapping_type_name()]

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
