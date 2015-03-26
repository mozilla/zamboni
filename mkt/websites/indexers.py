from operator import attrgetter

from mkt.search.indexers import BaseIndexer
from mkt.translations.models import attach_trans_dict
from mkt.translations.utils import format_translation_es


class WebsiteIndexer(BaseIndexer):
    translated_fields = ('description', 'short_title', 'title', 'url')

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
                'properties': {
                    'id': {'type': 'long'},
                    'category': cls.string_not_analyzed(),
                    'created': {'type': 'date', 'format': 'dateOptionalTime'},
                    'description': {'type': 'string',
                                    'analyzer': 'default_icu'},
                    'default_locale': cls.string_not_indexed(),
                    'icon_hash': cls.string_not_indexed(),
                    'icon_type': cls.string_not_indexed(),
                    'last_updated': {'format': 'dateOptionalTime',
                                     'type': 'date'},
                    'modified': {'type': 'date', 'format': 'dateOptionalTime'},
                    'short_title': {'type': 'string',
                                    'analyzer': 'default_icu'},
                    'title': {'type': 'string', 'analyzer': 'default_icu'},
                    # FIXME: Add custom analyzer for url, that strips http,
                    # https, maybe also www. and any .tld ?
                    'url': {'type': 'string', 'analyzer': 'simple'},

                    # FIXME: categories, regions, devices, status. Might need
                    # to refactor with webapps/indexers.py
                }
            }
        }

        # Add fields that we expect to return all translations.
        cls.attach_translation_mappings(mapping, cls.translated_fields)

        # FIXME: add indexed/analyzed translated fields mapping. Refactor with
        # webapps/indexers.py.
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
        doc['category'] = obj.categories if obj.categories else []

        doc['description'] = list(
            set(string for _, string in obj.translations[obj.description_id]))
        doc['short_title'] = list(
            set(string for _, string in obj.translations[obj.short_title_id]))
        doc['title'] = list(
            set(string for _, string in obj.translations[obj.title_id]))
        doc['url'] = list(
            set(string for _, string in obj.translations[obj.url_id]))

        # Handle localized fields.
        for field in cls.translated_fields:
            doc.update(format_translation_es(obj, field))

        return doc
