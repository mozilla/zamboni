"""
Indexers for FeedApp, FeedBrand, FeedCollection are for Curator Tools search.
"""
from amo.utils import attach_trans_dict

from mkt.feed.models import FeedApp, FeedBrand, FeedCollection
from mkt.search.indexers import BaseIndexer
from mkt.webapps.models import Webapp


class FeedAppIndexer(BaseIndexer):
    @classmethod
    def get_model(cls):
        """Returns the Django model this MappingType relates to"""
        return FeedApp

    @classmethod
    def get_mapping(cls):
        """Returns an Elasticsearch mapping for this MappingType"""
        return {
            'properties': {
                'id': {'type': 'integer'},
                'name': {'type': 'string', 'analyzer': 'default_icu'},
                'slug': {'type': 'string'},
                'type': {'type': 'string'},
            }
        }

    def extract_document(cls, obj_id, obj=None):
        """Converts this instance into an Elasticsearch document"""
        if obj is None:
            obj = cls.get_model().get(pk=obj_id)

        # Attach translations to app object for the app name.
        attach_trans_dict(Webapp, [obj.app])

        return {
            'id': obj.id,
            'name': list(set(string for _, string
                             in obj.app.translations[obj.app.name_id])),
            'slug': obj.slug,
            'type': obj.type,
        }


class FeedBrandIndexer(BaseIndexer):
    @classmethod
    def get_model(cls):
        return FeedBrand

    @classmethod
    def get_mapping(cls):
        return {
            'properties': {
                'id': {'type': 'integer'},
                'slug': {'type': 'string'},
                'type': {'type': 'string'},
            }
        }

    def extract_document(cls, obj_id, obj=None):
        if obj is None:
            obj = cls.get_model().get(pk=obj_id)

        return {
            'id': obj.id,
            'slug': obj.slug,
            'type': obj.type,
        }


class FeedCollectionIndexer(BaseIndexer):
    @classmethod
    def get_model(cls):
        return FeedCollection

    @classmethod
    def get_mapping(cls):
        return {
            'properties': {
                'id': {'type': 'integer'},
                'name': {'type': 'string', 'analyzer': 'default_icu'},
                'slug': {'type': 'string'},
                'type': {'type': 'string'},
            }
        }

    def extract_document(cls, obj_id, obj=None):
        if obj is None:
            obj = cls.get_model().get(pk=obj_id)

        attach_trans_dict(FeedCollection, [obj])

        return {
            'id': obj.id,
            'slug': obj.slug,
            'name': list(set(string for _, string
                             in obj.translations[obj.name_id])),
            'type': obj.type,
        }
