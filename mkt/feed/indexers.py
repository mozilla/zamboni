"""
Indexers for FeedApp, FeedBrand, FeedCollection, FeedShelf, FeedItem for
feed homepage and curation tool search.
"""
from collections import defaultdict

from amo.utils import attach_trans_dict

import mkt.carriers
import mkt.feed.constants as feed
import mkt.regions
from mkt.search.indexers import BaseIndexer
from mkt.translations.utils import format_translation_es
from mkt.webapps.models import Webapp


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
                    'background_color': {'type': 'string',
                                         'index': 'not_analyzed'},
                    'has_image': {'type': 'boolean'},
                    'item_type': {'type': 'string', 'index': 'not_analyzed'},
                    'preview': {'type': 'object', 'dynamic': 'true'},
                    'pullquote_attribution': {'type': 'string',
                                              'index': 'not_analyzed'},
                    'pullquote_rating': {'type': 'short'},
                    'pullquote_text': {'type': 'string',
                                       'analyzer': 'default_icu'},
                    'search_names': {'type': 'string',
                                     'analyzer': 'default_icu'},
                    'slug': {'type': 'string'},
                    'type': {'type': 'string', 'index': 'not_analyzed'},
                }
            }
        }

        return cls.attach_translation_mappings(mapping, ('description',))

    @classmethod
    def extract_document(cls, obj_id, obj=None):
        """Converts this instance into an Elasticsearch document"""
        if obj is None:
            obj = cls.get_model().get(pk=obj_id)

        # Attach translations for searching and indexing.
        attach_trans_dict(cls.get_model(), [obj])
        attach_trans_dict(Webapp, [obj.app])

        doc = {
            'id': obj.id,
            'app': obj.app_id,
            'background_color': obj.background_color,
            'has_image': obj.has_image,
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
            doc.update(format_translation_es(obj, field))

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
                    'item_type': {'type': 'string', 'index': 'not_analyzed'},
                    'slug': {'type': 'string'},
                    'type': {'type': 'string'},
                }
            }
        }

    @classmethod
    def extract_document(cls, obj_id, obj=None):
        if obj is None:
            obj = cls.get_model().get(pk=obj_id)

        return {
            'id': obj.id,
            'apps': list(obj.apps().values_list('id', flat=True)),
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
                    'group_apps': {'type': 'object', 'dynamic': 'true'},
                    'group_names': {'type': 'object', 'dynamic': 'true'},
                    'has_image': {'type': 'boolean'},
                    'item_type': {'type': 'string', 'index': 'not_analyzed'},
                    'search_names': {'type': 'string',
                                     'analyzer': 'default_icu'},
                    'slug': {'type': 'string'},
                    'type': {'type': 'string', 'index': 'not_analyzed'},
                }
            }
        }

        return cls.attach_translation_mappings(mapping, ('description',
                                                         'name'))

    @classmethod
    def extract_document(cls, obj_id, obj=None):
        from mkt.feed.models import FeedCollection, FeedCollectionMembership

        if obj is None:
            obj = cls.get_model().get(pk=obj_id)

        attach_trans_dict(cls.get_model(), [obj])

        doc = {
            'id': obj.id,
            'apps': list(obj.apps().values_list('id', flat=True)),
            'group_apps': {},  # Map of app IDs to index in group_names below.
            'group_names': [],  # List of ES-serialized group names.
            'has_image': obj.has_image,
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
                grp_translation = format_translation_es(member, 'group')
                if grp_translation not in doc['group_names']:
                    doc['group_names'].append(grp_translation)

                doc['group_apps'][member.app_id] = doc['group_names'].index(
                    grp_translation)

        # Handle localized fields.
        for field in ('description', 'name'):
            doc.update(format_translation_es(obj, field))

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
                    'background_color': {'type': 'string',
                                         'index': 'not_analyzed'},
                    'carrier': {'type': 'string', 'index': 'not_analyzed'},
                    'has_image': {'type': 'boolean'},
                    'item_type': {'type': 'string', 'index': 'not_analyzed'},
                    'region': {'type': 'string', 'index': 'not_analyzed'},
                    'search_names': {'type': 'string',
                                     'analyzer': 'default_icu'},
                    'slug': {'type': 'string'},
                }
            }
        }

        return cls.attach_translation_mappings(mapping, ('description',
                                                         'name'))

    @classmethod
    def extract_document(cls, obj_id, obj=None):
        from mkt.feed.models import FeedShelf

        if obj is None:
            obj = cls.get_model().get(pk=obj_id)

        attach_trans_dict(cls.get_model(), [obj])

        doc = {
            'id': obj.id,
            'apps': list(obj.apps().values_list('id', flat=True)),
            'background_color': obj.background_color,
            'carrier': mkt.carriers.CARRIER_CHOICE_DICT[obj.carrier].slug,
            'has_image': obj.has_image,
            'item_type': feed.FEED_TYPE_SHELF,
            'region': mkt.regions.REGIONS_CHOICES_ID_DICT[obj.region].slug,
            'search_names': list(set(string for _, string
                                     in obj.translations[obj.name_id])),
            'slug': obj.slug,
        }

        # Handle localized fields.
        for field in ('description', 'name'):
            doc.update(format_translation_es(obj, field))

        return doc


class FeedItemIndexer(BaseIndexer):
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
                    'item_type': {'type': 'string', 'index': 'not_analyzed'},
                    'region': {'type': 'integer'},
                    'shelf': {'type': 'long'},
                }
            }
        }

    @classmethod
    def extract_document(cls, obj_id, obj=None):
        from mkt.feed.models import FeedItem

        if obj is None:
            obj = cls.get_model().get(pk=obj_id)

        return {
            'id': obj.id,
            'app': obj.app_id if obj.item_type == feed.FEED_TYPE_APP
                   else None,
            'brand': obj.brand_id if obj.item_type == feed.FEED_TYPE_BRAND
                     else None,
            'carrier': obj.carrier,
            'category': obj.category,
            'collection': obj.collection_id if
                          obj.item_type == feed.FEED_TYPE_COLL else None,
            'item_type': obj.item_type,
            'region': obj.region,
            'shelf': obj.shelf_id if obj.item_type == feed.FEED_TYPE_SHELF
                     else None,
        }
