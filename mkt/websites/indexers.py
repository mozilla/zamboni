from operator import attrgetter

from mkt.search.indexers import BaseIndexer
from mkt.translations.models import attach_trans_dict


class WebsiteIndexer(BaseIndexer):
    translated_fields = ('description', 'short_title', 'title', 'url')
    fields_with_language_analyzers = ('description', 'title')

    @classmethod
    def get_mapping_type_name(cls):
        return 'mkt_website'

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
                    'last_updated': {'format': 'dateOptionalTime',
                                     'type': 'date'},
                    'modified': {'type': 'date', 'format': 'dateOptionalTime'},
                    'region_exclusions': {'type': 'short'},
                    'short_title': {'type': 'string',
                                    'analyzer': 'default_icu'},
                    'title': {'type': 'string',
                              'analyzer': 'default_icu',
                              'position_offset_gap': 100},
                    # FIXME: Add custom analyzer for url, that strips http,
                    # https, maybe also www. and any .tld ?
                    'url': {'type': 'string', 'analyzer': 'simple'},
                    # FIXME: status.
                }
            }
        }

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

        attrs = ('created', 'default_locale', 'id', 'icon_hash', 'icon_type',
                 'last_updated', 'modified')
        doc = dict(zip(attrs, attrgetter(*attrs)(obj)))

        doc['id'] = obj.pk
        doc['category'] = obj.categories or []
        doc['device'] = obj.devices or []
        doc['region_exclusions'] = obj.region_exclusions or []

        # Handle localized fields. This adds both the field used for search and
        # the one with all translations for the API.
        for field in cls.translated_fields:
            doc.update(cls.extract_field_translations(
                obj, field, include_field_for_search=True))

        # Handle language-specific analyzers.
        for field in cls.fields_with_language_analyzers:
            doc.update(cls.extract_field_analyzed_translations(obj, field))

        return doc
