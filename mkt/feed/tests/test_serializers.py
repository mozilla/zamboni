# -*- coding: utf-8 -*-
from collections import defaultdict

from nose.tools import eq_
from rest_framework.serializers import ValidationError

import amo
import amo.tests

import mkt.feed.constants as feed
from mkt.feed import serializers
from mkt.feed.constants import COLLECTION_LISTING, COLLECTION_PROMO
from mkt.feed.models import FeedBrand, FeedShelf
from mkt.feed.tests.test_models import FeedAppMixin, FeedTestMixin
from mkt.feed.serializers import (FeedAppSerializer, FeedBrandSerializer,
                                  FeedCollectionSerializer,
                                  FeedShelfSerializer, FeedItemSerializer)
from mkt.regions import RESTOFWORLD
from mkt.webapps.models import Preview
from mkt.webapps.indexers import WebappIndexer


class TestFeedAppSerializer(FeedTestMixin, amo.tests.TestCase):

    def test_basic(self):
        data = {
            'app': 337141,
            'background_color': '#B90000',
            'type': 'icon',
            'description': {
                'en-US': u'pan-fried potatoes'
            },
            'slug': 'aaa'
        }
        serializer = serializers.FeedAppSerializer(data=data)
        assert serializer.is_valid()


class TestFeedAppESSerializer(FeedTestMixin, amo.tests.TestCase):

    def setUp(self):
        self.feedapp = self.feed_app_factory(
            app_type=feed.FEEDAPP_DESC, description={'en-US': 'test'})
        self.feedapp.update(preview=Preview.objects.create(
            addon=self.feedapp.app, sizes={'thumbnail': [50, 50]}))

        self.data_es = self.feedapp.get_indexer().extract_document(
            None, obj=self.feedapp)

        self.app_map = {
            self.feedapp.app_id: WebappIndexer.extract_document(
                self.feedapp.app_id)
        }

    def test_deserialize(self):
        data = serializers.FeedAppESSerializer(self.data_es, context={
            'app_map': self.app_map,
            'request': amo.tests.req_factory_factory('')
        }).data
        eq_(data['app']['id'], self.feedapp.app_id)
        eq_(data['description']['en-US'], 'test')
        eq_(data['preview'], {
            'id': self.feedapp.preview.id,
            'thumbnail_size': [50, 50],
            'thumbnail_url': self.feedapp.preview.thumbnail_url})

    def test_deserialize_many(self):
        data = serializers.FeedAppESSerializer(
            [self.data_es, self.data_es], context={
                'app_map': self.app_map,
                'request': amo.tests.req_factory_factory('')
        }, many=True).data
        eq_(data[0]['app']['id'], self.feedapp.app_id)
        eq_(data[1]['description']['en-US'], 'test')


class TestFeedBrandSerializer(FeedTestMixin, amo.tests.TestCase):

    def setUp(self):
        self.app_ids = [amo.tests.app_factory().id for i in range(3)]
        self.brand = self.feed_brand_factory(app_ids=self.app_ids)
        super(TestFeedBrandSerializer, self).setUp()

    def test_deserialize(self):
        data = serializers.FeedBrandSerializer(self.brand).data
        eq_(data['slug'], self.brand.slug)
        eq_(data['layout'], self.brand.layout)
        eq_(data['type'], self.brand.type)
        self.assertSetEqual([app['id'] for app in data['apps']], self.app_ids)


class TestFeedBrandESSerializer(FeedTestMixin, amo.tests.TestCase):

    def setUp(self):
        self.apps = [amo.tests.app_factory() for i in range(3)]
        self.app_ids = [app.id for app in self.apps]

        self.brand = self.feed_brand_factory(app_ids=self.app_ids)
        self.data_es = self.brand.get_indexer().extract_document(
            None, obj=self.brand)

        self.app_map = dict((app.id, WebappIndexer.extract_document(app.id))
                            for app in self.apps)

    def test_deserialize(self):
        data = serializers.FeedBrandESSerializer(self.data_es, context={
            'app_map': self.app_map,
            'request': amo.tests.req_factory_factory('')
        }).data
        self.assertSetEqual([app['id'] for app in data['apps']],
                            [app.id for app in self.apps])
        eq_(data['type'], self.brand.type)


class TestFeedCollectionSerializer(FeedTestMixin, amo.tests.TestCase):

    def setUp(self):
        super(TestFeedCollectionSerializer, self).setUp()
        self.data = {
            'background_color': '#FF4E00',
            'name': {'en-US': 'Potato'},
            'description': {'en-US': 'Potato, tomato'},
            'type': COLLECTION_PROMO
        }

    def validate(self, **attrs):
        return (serializers.FeedCollectionSerializer()
                .validate_background_color(attrs=self.data,
                                           source='background_color'))

    def test_validate_promo_bg(self):
        self.validate()

    def test_validate_promo_nobg(self):
        del self.data['background_color']
        with self.assertRaises(ValidationError):
            self.validate()

    def test_validate_listing_bg(self):
        self.data['type'] = COLLECTION_LISTING
        self.validate()

    def test_validate_listing_nobg(self):
        self.data['type'] = COLLECTION_LISTING
        del self.data['background_color']
        self.validate()


class TestFeedCollectionESSerializer(FeedTestMixin, amo.tests.TestCase):

    def setUp(self):
        self.apps = [amo.tests.app_factory() for i in range(3)]
        self.app_ids = [app.id for app in self.apps]

        self.collection = self.feed_collection_factory(
            app_ids=self.app_ids, description={'de': 'test'},
            name={'en-US': 'test'})
        self.data_es = self.collection.get_indexer().extract_document(
            None, obj=self.collection)

        self.app_map = dict((app.id, WebappIndexer.extract_document(app.id))
                            for app in self.apps)

    def test_deserialize(self):
        data = serializers.FeedCollectionESSerializer(self.data_es, context={
            'app_map': self.app_map,
            'request': amo.tests.req_factory_factory('')
        }).data
        self.assertSetEqual([app['id'] for app in data['apps']],
                            [app.id for app in self.apps])
        eq_(data['description']['de'], 'test')
        eq_(data['name']['en-US'], 'test')
        return data

    def test_deserialize_grouped_apps(self):
        self.collection = self.feed_collection_factory(
            app_ids=self.app_ids, grouped=True, description={'de': 'test'},
            name={'en-US': 'test'})
        self.data_es = self.collection.get_indexer().extract_document(
            None, obj=self.collection)
        data = self.test_deserialize()
        for i, app in enumerate(data['apps']):
            group = app['group']['en-US']
            if not i == 2:
                eq_(group, 'first-group')
            else:
                eq_(group, 'second-group')


class TestFeedShelfSerializer(FeedTestMixin, amo.tests.TestCase):

    def setUp(self):
        self.app_ids = [amo.tests.app_factory().id for i in range(3)]
        self.shelf = self.feed_shelf_factory(app_ids=self.app_ids)
        super(TestFeedShelfSerializer, self).setUp()

    def test_deserialize(self):
        data = serializers.FeedShelfSerializer(self.shelf).data
        eq_(data['slug'], self.shelf.slug)
        self.assertSetEqual([app['id'] for app in data['apps']], self.app_ids)


class TestFeedShelfESSerializer(FeedTestMixin, amo.tests.TestCase):

    def setUp(self):
        self.apps = [amo.tests.app_factory() for i in range(3)]
        self.app_ids = [app.id for app in self.apps]

        self.shelf = self.feed_shelf_factory(
            app_ids=self.app_ids, description={'de': 'test'},
            name={'en-US': 'test'})
        self.data_es = self.shelf.get_indexer().extract_document(
            None, obj=self.shelf)

        self.app_map = dict((app.id, WebappIndexer.extract_document(app.id))
                            for app in self.apps)

    def test_deserialize(self):
        data = serializers.FeedShelfESSerializer(self.data_es, context={
            'app_map': self.app_map,
            'request': amo.tests.req_factory_factory('')
        }).data
        self.assertSetEqual([app['id'] for app in data['apps']],
                            [app.id for app in self.apps])
        eq_(data['carrier'], 'telefonica')
        eq_(data['region'], 'restofworld')
        eq_(data['description']['de'], 'test')
        eq_(data['name']['en-US'], 'test')


class TestFeedItemSerializer(FeedAppMixin, amo.tests.TestCase):

    def setUp(self):
        super(TestFeedItemSerializer, self).setUp()
        self.create_feedapps()

    def serializer(self, item=None, **context):
        if not item:
            return serializers.FeedItemSerializer(context=context)
        return serializers.FeedItemSerializer(item, context=context)

    def validate(self, **attrs):
        return self.serializer().validate(attrs=attrs)

    def test_validate_passes(self):
        self.validate(app=self.feedapps[0])

    def test_validate_fails_no_items(self):
        with self.assertRaises(ValidationError):
            self.validate(app=None)

    def validate_shelf(self, **attrs):
        shelf = FeedShelf.objects.create(carrier=1, region=2)
        data = {
            'carrier': 'telefonica',
            'region': 'us',
            'shelf': shelf.id
        }
        data.update(attrs)
        return self.serializer().validate_shelf(data, 'shelf')

    def test_validate_shelf_passes(self):
        self.validate_shelf()

    def test_validate_shelf_fails_region(self):
        with self.assertRaises(ValidationError):
            self.validate_shelf(region='br')

    def test_validate_shelf_fails_carrier(self):
        with self.assertRaises(ValidationError):
            self.validate_shelf(carrier='telenor')

    def test_region_handles_worldwide(self):
        data = {
            'region': 'worldwide',
            'item_type': 'app',
            'app': self.feedapps[0].id,
        }
        serializer = serializers.FeedItemSerializer(data=data)
        assert serializer.is_valid()
        assert serializer.object.region == RESTOFWORLD.id


class TestFeedItemESSerializer(FeedTestMixin, amo.tests.TestCase):

    def setUp(self):
        self.feed = self.feed_factory()
        self.data_es = [
            feed_item.get_indexer().extract_document(None, obj=feed_item)
            for feed_item in self.feed]

        # Denormalize feed elements into the serializer context.
        self.app_map = {}
        self.feed_element_map = defaultdict(dict)
        for i, feed_item in enumerate(self.data_es):
            feed_element = getattr(self.feed[i], feed_item['item_type'])
            self.feed_element_map[feed_item['item_type']][feed_element.id] = (
                feed_element.get_indexer().extract_document(None,
                                                            obj=feed_element))

            # Denormalize apps into serializer context.
            if hasattr(feed_element, 'apps'):
                for app in feed_element.apps():
                    self.app_map[app.id] = WebappIndexer.extract_document(
                        None, obj=app)
            else:
                self.app_map[feed_element.app_id] = (
                    WebappIndexer.extract_document(feed_element.app_id))

    def test_deserialize_many(self):
        data = serializers.FeedItemESSerializer(self.data_es, context={
            'app_map': self.app_map,
            'feed_element_map': self.feed_element_map,
            'request': amo.tests.req_factory_factory('')
        }, many=True).data

        eq_(data[0]['app']['app']['id'], self.feed[0].app.app.id)

        eq_(data[1]['brand']['apps'][0]['id'],
            self.feed[1].brand.apps()[0].id)

        eq_(data[2]['collection']['apps'][0]['id'],
            self.feed[2].collection.apps()[0].id)

        eq_(data[3]['shelf']['apps'][0]['id'],
            self.feed[3].shelf.apps()[0].id)
