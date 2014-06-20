"""
Indexers for FeedApp, FeedBrand, FeedCollection are for Curator Tools search.
"""
from amo.utils import attach_trans_dict

import mkt.carriers
import mkt.regions
from mkt.search.indexers import BaseIndexer
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

        return {
            doc_type: {
                'properties': {
                    'id': {'type': 'integer'},
                    'name': {'type': 'string', 'analyzer': 'default_icu'},
                    'slug': {'type': 'string'},
                    'type': {'type': 'string', 'index': 'not_analyzed'},
                }
            }
        }

    @classmethod
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
        from mkt.feed.models import FeedBrand
        return FeedBrand

    @classmethod
    def get_mapping(cls):
        doc_type = cls.get_mapping_type_name()

        return {
            doc_type: {
                'properties': {
                    'id': {'type': 'integer'},
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

        return {
            doc_type: {
                'properties': {
                    'id': {'type': 'integer'},
                    'name': {'type': 'string', 'analyzer': 'default_icu'},
                    'slug': {'type': 'string'},
                    'type': {'type': 'string', 'index': 'not_analyzed'},
                }
            }
        }

    @classmethod
    def extract_document(cls, obj_id, obj=None):
        from mkt.feed.models import FeedCollection

        if obj is None:
            obj = cls.get_model().get(pk=obj_id)

        attach_trans_dict(FeedCollection, [obj])

        return {
            'id': obj.id,
            'name': list(set(string for _, string
                             in obj.translations[obj.name_id])),
            'slug': obj.slug,
            'type': obj.type,
        }


class FeedShelfIndexer(BaseIndexer):
    @classmethod
    def get_model(cls):
        from mkt.feed.models import FeedShelf
        return FeedShelf

    @classmethod
    def get_mapping(cls):
        doc_type = cls.get_mapping_type_name()

        return {
            doc_type: {
                'properties': {
                    'id': {'type': 'integer'},
                    'name': {'type': 'string', 'analyzer': 'default_icu'},
                    'slug': {'type': 'string'},
                    'carrier': {'type': 'string', 'index': 'not_analyzed'},
                    'region': {'type': 'string', 'index': 'not_analyzed'},
                }
            }
        }

    @classmethod
    def extract_document(cls, obj_id, obj=None):
        from mkt.feed.models import FeedShelf

        if obj is None:
            obj = cls.get_model().get(pk=obj_id)

        attach_trans_dict(FeedShelf, [obj])

        return {
            'id': obj.id,
            'name': list(set(string for _, string
                             in obj.translations[obj.name_id])),
            'slug': obj.slug,
            'carrier': mkt.carriers.CARRIER_CHOICE_DICT[obj.carrier].slug,
            'region': mkt.regions.REGIONS_CHOICES_ID_DICT[obj.region].slug,
        }
