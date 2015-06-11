"""
Indexers for FeedApp, FeedBrand, FeedCollection, FeedShelf, FeedItem for
feed homepage and curation tool search.
"""
import mkt.carriers
import mkt.feed.constants as feed
import mkt.regions
from mkt.search.indexers import BaseIndexer
from mkt.translations.models import attach_trans_dict
from mkt.webapps.models import Webapp


def get_slug_multifield():
    # TODO: convert to new syntax on ES 1.0+.
    return {
        'type': 'multi_field',
        'fields': {
            'slug': {'type': 'string'},
            'raw': {'type': 'string', 'index': 'not_analyzed'},
        }
    }


class FeedAppIndexer(BaseIndexer):
    @classmethod
    def get_model(cls):
        """Returns the Django model this MappingType relates to"""
        from mkt.feed.models import FeedApp
        return FeedApp

    @classmethod
    def get_mapping(cls):
        """Returns an Elasticsearch mapping for this MappingType"""
        doc_type = cls.get_mapping_type_name()

        mapping = {
            doc_type: {
                'properties': {
                    'id': {'type': 'long'},
                    'app': {'type': 'long'},
                    'background_color': cls.string_not_analyzed(),
                    'color': cls.string_not_analyzed(),
                    'created': {'type': 'date', 'format': 'dateOptionalTime'},
                    'image_hash': cls.string_not_analyzed(),
                    'item_type': cls.string_not_analyzed(),
                    'preview': {'type': 'object', 'dynamic': 'true'},
                    'pullquote_attribution': cls.string_not_analyzed(),
                    'pullquote_rating': {'type': 'short'},
                    'pullquote_text': {'type': 'string',
                                       'analyzer': 'default_icu'},
                    'search_names': {'type': 'string',
                                     'analyzer': 'default_icu'},
                    'slug': get_slug_multifield(),
                    'type': cls.string_not_analyzed(),
                }
            }
        }

        return cls.attach_translation_mappings(mapping, ('description',))

    @classmethod
    def extract_document(cls, pk=None, obj=None):
        """Converts this instance into an Elasticsearch document"""
        if obj is None:
            obj = cls.get_model().objects.get(pk=pk)

        # Attach translations for searching and indexing.
        attach_trans_dict(cls.get_model(), [obj])
        attach_trans_dict(Webapp, [obj.app])

        doc = {
            'id': obj.id,
            'app': obj.app_id,
            'background_color': obj.background_color,
            'color': obj.color,
            'created': obj.created,
            'image_hash': obj.image_hash,
            'item_type': feed.FEED_TYPE_APP,
            'preview': {'id': obj.preview.id,
                        'thumbnail_size': obj.preview.thumbnail_size,
                        'thumbnail_url': obj.preview.thumbnail_url}
            if getattr(obj, 'preview') else None,
            'pullquote_attribution': obj.pullquote_attribution,
            'pullquote_rating': obj.pullquote_rating,
            'search_names': list(
                set(string for _, string
                    in obj.app.translations[obj.app.name_id])),
            'slug': obj.slug,
            'type': obj.type,
        }

        # Handle localized fields.
        for field in ('description', 'pullquote_text'):
            doc.update(cls.extract_field_translations(obj, field))

        return doc


class FeedBrandIndexer(BaseIndexer):
    @classmethod
    def get_model(cls):
        from mkt.feed.models import FeedBrand
        return FeedBrand

    @classmethod
    def get_mapping(cls):
        doc_type = cls.get_mapping_type_name()

        return {
            doc_type: {
                'properties': {
                    'id': {'type': 'long'},
                    'apps': {'type': 'long'},
                    'created': {'type': 'date', 'format': 'dateOptionalTime'},
                    'layout': cls.string_not_analyzed(),
                    'item_type': cls.string_not_analyzed(),
                    'slug': get_slug_multifield(),
                    'type': {'type': 'string'},
                }
            }
        }

    @classmethod
    def extract_document(cls, pk=None, obj=None):
        if obj is None:
            obj = cls.get_model().objects.get(pk=pk)

        return {
            'id': obj.id,
            'apps': list(obj.apps().values_list('id', flat=True)),
            'created': obj.created,
            'layout': obj.layout,
            'item_type': feed.FEED_TYPE_BRAND,
            'slug': obj.slug,
            'type': obj.type,
        }


class FeedCollectionIndexer(BaseIndexer):
    @classmethod
    def get_model(cls):
        from mkt.feed.models import FeedCollection
        return FeedCollection

    @classmethod
    def get_mapping(cls):
        doc_type = cls.get_mapping_type_name()

        mapping = {
            doc_type: {
                'properties': {
                    'id': {'type': 'long'},
                    'apps': {'type': 'long'},
                    'created': {'type': 'date', 'format': 'dateOptionalTime'},
                    'background_color': cls.string_not_analyzed(),
                    'color': cls.string_not_analyzed(),
                    'group_apps': {'type': 'object', 'dynamic': 'true'},
                    'group_names': {'type': 'object', 'dynamic': 'true'},
                    'image_hash': cls.string_not_analyzed(),
                    'item_type': cls.string_not_analyzed(),
                    'search_names': {'type': 'string',
                                     'analyzer': 'default_icu'},
                    'slug': get_slug_multifield(),
                    'type': cls.string_not_analyzed(),
                }
            }
        }

        return cls.attach_translation_mappings(mapping, ('description',
                                                         'name'))

    @classmethod
    def extract_document(cls, pk=None, obj=None):
        from mkt.feed.models import FeedCollectionMembership

        if obj is None:
            obj = cls.get_model().objects.get(pk=pk)

        attach_trans_dict(cls.get_model(), [obj])

        doc = {
            'id': obj.id,
            'apps': list(obj.apps().values_list('id', flat=True)),
            'background_color': obj.background_color,
            'color': obj.color,
            'created': obj.created,
            'group_apps': {},  # Map of app IDs to index in group_names below.
            'group_names': [],  # List of ES-serialized group names.
            'image_hash': obj.image_hash,
            'item_type': feed.FEED_TYPE_COLL,
            'search_names': list(
                set(string for _, string
                    in obj.translations[obj.name_id])),
            'slug': obj.slug,
            'type': obj.type,
        }

        # Grouped apps. Key off of translation, pointed to app IDs.
        memberships = obj.feedcollectionmembership_set.all()
        attach_trans_dict(FeedCollectionMembership, memberships)
        for member in memberships:
            if member.group:
                group_translation = cls.extract_field_translations(member,
                                                                   'group')
                if group_translation not in doc['group_names']:
                    doc['group_names'].append(group_translation)

                doc['group_apps'][member.app_id] = (
                    doc['group_names'].index(group_translation))

        # Handle localized fields.
        for field in ('description', 'name'):
            doc.update(cls.extract_field_translations(obj, field))

        return doc


class FeedShelfIndexer(BaseIndexer):
    @classmethod
    def get_model(cls):
        from mkt.feed.models import FeedShelf
        return FeedShelf

    @classmethod
    def get_mapping(cls):
        doc_type = cls.get_mapping_type_name()

        mapping = {
            doc_type: {
                'properties': {
                    'id': {'type': 'long'},
                    'apps': {'type': 'long'},
                    'carrier': cls.string_not_analyzed(),
                    'created': {'type': 'date', 'format': 'dateOptionalTime'},
                    'group_apps': {'type': 'object', 'dynamic': 'true'},
                    'group_names': {'type': 'object', 'dynamic': 'true'},
                    'image_hash': cls.string_not_analyzed(),
                    'image_landing_hash': cls.string_not_analyzed(),
                    'item_type': cls.string_not_analyzed(),
                    'region': cls.string_not_analyzed(),
                    'search_names': {'type': 'string',
                                     'analyzer': 'default_icu'},
                    'slug': get_slug_multifield(),
                }
            }
        }

        return cls.attach_translation_mappings(mapping, ('description',
                                                         'name'))

    @classmethod
    def extract_document(cls, pk=None, obj=None):
        from mkt.feed.models import FeedShelfMembership

        if obj is None:
            obj = cls.get_model().get(pk=pk)

        attach_trans_dict(cls.get_model(), [obj])

        doc = {
            'id': obj.id,
            'apps': list(obj.apps().values_list('id', flat=True)),
            'carrier': mkt.carriers.CARRIER_CHOICE_DICT[obj.carrier].slug,
            'created': obj.created,
            'group_apps': {},  # Map of app IDs to index in group_names below.
            'group_names': [],  # List of ES-serialized group names.
            'image_hash': obj.image_hash,
            'image_landing_hash': obj.image_landing_hash,
            'item_type': feed.FEED_TYPE_SHELF,
            'region': mkt.regions.REGIONS_CHOICES_ID_DICT[obj.region].slug,
            'search_names': list(set(string for _, string
                                     in obj.translations[obj.name_id])),
            'slug': obj.slug,
        }

        # Grouped apps. Key off of translation, pointed to app IDs.
        memberships = obj.feedshelfmembership_set.all()
        attach_trans_dict(FeedShelfMembership, memberships)
        for member in memberships:
            if member.group:
                group_translation = cls.extract_field_translations(member,
                                                                   'group')
                if group_translation not in doc['group_names']:
                    doc['group_names'].append(group_translation)

                doc['group_apps'][member.app_id] = (
                    doc['group_names'].index(group_translation))

        # Handle localized fields.
        for field in ('description', 'name'):
            doc.update(cls.extract_field_translations(obj, field))

        return doc


class FeedItemIndexer(BaseIndexer):

    chunk_size = 1000

    @classmethod
    def get_model(cls):
        from mkt.feed.models import FeedItem
        return FeedItem

    @classmethod
    def get_mapping(cls):
        doc_type = cls.get_mapping_type_name()

        return {
            doc_type: {
                'properties': {
                    'id': {'type': 'long'},
                    'app': {'type': 'long'},
                    'brand': {'type': 'long'},
                    'carrier': {'type': 'integer'},
                    'category': {'type': 'integer'},
                    'collection': {'type': 'long'},
                    'item_type': cls.string_not_analyzed(),
                    'order': {'type': 'integer'},
                    'region': {'type': 'integer'},
                    'shelf': {'type': 'long'},
                }
            }
        }

    @classmethod
    def extract_document(cls, pk=None, obj=None):
        if obj is None:
            obj = cls.get_model().objects.get(pk=pk)

        return {
            'id': obj.id,
            'app': (obj.app_id if obj.item_type == feed.FEED_TYPE_APP
                    else None),
            'brand': (obj.brand_id if obj.item_type == feed.FEED_TYPE_BRAND
                      else None),
            'carrier': obj.carrier,
            'category': obj.category,
            'collection': (obj.collection_id if
                           obj.item_type == feed.FEED_TYPE_COLL else None),
            'item_type': obj.item_type,
            # If no order, put it at end. Make sure order > 0 since we do a
            # ES reciprocal modifier query.
            'order': obj.order + 1 if obj.order is not None else 100,
            'region': obj.region,
            'shelf': (obj.shelf_id if obj.item_type == feed.FEED_TYPE_SHELF
                      else None),
        }
