from operator import attrgetter

from mkt.search.indexers import BaseIndexer
from mkt.tags.models import attach_tags
from mkt.translations.models import attach_trans_dict


class WebsiteIndexer(BaseIndexer):
    translated_fields = ('description', 'name', 'short_name', 'title')
    fields_with_language_analyzers = ('description', 'name', 'short_name')
    hidden_fields = (
        '*.raw',
        '*_sort',
        'popularity_*',
        'trending_*',
        'boost',
        # 'name', 'short_name' and 'description', as well as their locale
        # variants ('name_l10n_<language>', etc.) are only used for the query
        # matches, and are never returned to the client through the API. The
        # fields that are returned to the API are '*_translations'.
        'description',
        'name',
        'short_name',
        'description_l10n_*',
        'name_l10n_*',
        'short_name_l10n_*',
        # Title is not analyzed with language-specific analyzers but again, we
        # need `title_translations` for the API, `title` is only used for
        # querying.
        'title',
    )

    @classmethod
    def get_mapping_type_name(cls):
        return 'website'

    @classmethod
    def get_model(cls):
        """Returns the Django model this MappingType relates to"""
        from mkt.websites.models import Website
        return Website

    @classmethod
    def get_mapping(cls):
        """Returns an Elasticsearch mapping for this MappingType"""
        doc_type = cls.get_mapping_type_name()

        mapping = {
            doc_type: {
                '_all': {'enabled': False},
                'properties': {
                    'id': {'type': 'long'},
                    'category': cls.string_not_analyzed(),
                    'created': {'type': 'date', 'format': 'dateOptionalTime'},
                    'description': {'type': 'string',
                                    'analyzer': 'default_icu',
                                    'position_offset_gap': 100},
                    'default_locale': cls.string_not_indexed(),
                    'device': {'type': 'byte'},
                    'icon_hash': cls.string_not_indexed(),
                    'icon_type': cls.string_not_indexed(),
                    'is_disabled': {'type': 'boolean'},
                    'last_updated': {'format': 'dateOptionalTime',
                                     'type': 'date'},
                    'modified': {'type': 'date', 'format': 'dateOptionalTime'},
                    'name': {
                        'type': 'string',
                        'analyzer': 'default_icu',
                        'position_offset_gap': 100,
                        # For exact matches. Referenced as `name.raw`.
                        'fields': {
                            'raw': cls.string_not_analyzed(
                                position_offset_gap=100)
                        },
                    },
                    # Name for sorting.
                    'name_sort': cls.string_not_analyzed(doc_values=True),
                    'region_exclusions': {'type': 'short'},
                    'short_name': {'type': 'string',
                                   'analyzer': 'default_icu'},
                    'status': {'type': 'byte'},
                    'tags': {'type': 'string', 'analyzer': 'simple'},
                    'title': {
                        'type': 'string',
                        'analyzer': 'default_icu',
                        'position_offset_gap': 100,
                    },
                    # FIXME: Add custom analyzer for url, that strips http,
                    # https, maybe also www. and any .tld ?
                    'url': {'type': 'string', 'analyzer': 'simple'},
                }
            }
        }

        # Attach boost field, because we are going to need search by relevancy.
        cls.attach_boost_mapping(mapping)

        # Attach popularity and trending.
        cls.attach_trending_and_popularity_mappings(mapping)

        # Add extra mapping for translated fields, containing the "raw"
        # translations.
        cls.attach_translation_mappings(mapping, cls.translated_fields)

        # Add language-specific analyzers.
        cls.attach_language_specific_analyzers(
            mapping, cls.fields_with_language_analyzers)

        return mapping

    @classmethod
    def extract_document(cls, pk=None, obj=None):
        """Converts this instance into an Elasticsearch document"""
        if obj is None:
            obj = cls.get_model().objects.get(pk=pk)

        # Attach translations for searching and indexing.
        attach_trans_dict(cls.get_model(), [obj])

        # Attach tags (keywords).
        attach_tags([obj], m2m_name='keywords')

        attrs = ('created', 'default_locale', 'id', 'icon_hash', 'icon_type',
                 'is_disabled', 'last_updated', 'modified', 'status', 'url')
        doc = dict(zip(attrs, attrgetter(*attrs)(obj)))

        doc['category'] = obj.categories or []
        doc['device'] = obj.devices or []
        doc['name_sort'] = unicode(obj.name).lower()
        doc['region_exclusions'] = obj.region_exclusions or []
        doc['tags'] = getattr(obj, 'keywords_list', [])

        # Add boost, popularity, trending values.
        doc.update(cls.extract_popularity_trending_boost(obj))

        # Handle localized fields. This adds both the field used for search and
        # the one with all translations for the API.
        for field in cls.translated_fields:
            doc.update(cls.extract_field_translations(
                obj, field, include_field_for_search=True))

        # Handle language-specific analyzers.
        for field in cls.fields_with_language_analyzers:
            doc.update(cls.extract_field_analyzed_translations(obj, field))

        return doc
