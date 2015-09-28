from operator import attrgetter

from django.db.models import Min

from mkt.constants.base import STATUS_PUBLIC
from mkt.search.indexers import BaseIndexer
from mkt.translations.models import attach_trans_dict


class ExtensionIndexer(BaseIndexer):
    translated_fields = ('description', 'name', )
    fields_with_language_analyzers = ('description', 'name', )

    # "Hidden" fields are never returned to the client, they are for internal
    # use by ES only.
    hidden_fields = (
        '*.raw',
        '*_sort',
        # 'name', as well as its locale variants ('name_l10n_<language>', etc.)
        # are only used for the query matches, and are never returned to the
        # client through the API. The fields that are returned to the API are
        # '*_translations'.
        'name',
        'name_l10n_*',
    )

    @classmethod
    def get_mapping_type_name(cls):
        return 'extension'

    @classmethod
    def get_model(cls):
        """Returns the Django model this MappingType relates to"""
        from mkt.extensions.models import Extension
        return Extension

    @classmethod
    def get_mapping(cls):
        """Returns an Elasticsearch mapping for this MappingType"""
        doc_type = cls.get_mapping_type_name()

        mapping = {
            doc_type: {
                '_all': {'enabled': False},
                'properties': {
                    'id': {'type': 'long'},
                    'created': {'type': 'date', 'format': 'dateOptionalTime'},
                    'default_language': cls.string_not_indexed(),
                    'description': {
                        'type': 'string',
                        'analyzer': 'default_icu',
                        'position_offset_gap': 100,
                    },
                    'is_deleted': {'type': 'boolean'},
                    'is_disabled': {'type': 'boolean'},
                    'last_updated': {'format': 'dateOptionalTime',
                                     'type': 'date'},
                    'latest_public_version': {
                        'type': 'object',
                        'properties': {
                            'id': {'type': 'long'},
                            'created': {'type': 'date',
                                        'format': 'dateOptionalTime'},
                            'size': {'type': 'long'},
                            'version': cls.string_not_indexed(),
                        }
                    },
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
                    'reviewed': {'format': 'dateOptionalTime', 'type': 'date',
                                 'doc_values': True},
                    'guid': cls.string_not_analyzed(),
                    'slug': {'type': 'string'},
                    'status': {'type': 'byte'},
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

        attrs = ('created', 'default_language', 'id', 'last_updated',
                 'modified', 'slug', 'status')
        doc = dict(zip(attrs, attrgetter(*attrs)(obj)))

        doc['guid'] = unicode(obj.uuid)
        doc['is_deleted'] = obj.deleted
        doc['is_disabled'] = obj.disabled
        if obj.status == STATUS_PUBLIC:
            doc['latest_public_version'] = {
                'id': obj.latest_public_version.pk,
                'created': obj.latest_public_version.created,
                'size': obj.latest_public_version.size,
                'version': obj.latest_public_version.version
            }
        else:
            doc['latest_public_version'] = None
        doc['name_sort'] = unicode(obj.name).lower()
        # Find the first reviewed date (used in sort).
        doc['reviewed'] = obj.versions.public().aggregate(
            Min('reviewed')).get('reviewed__min')

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
