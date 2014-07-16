# -*- coding: utf-8 -*-
from nose.tools import eq_
from rest_framework import serializers

import amo
import amo.tests

from mkt.feed.constants import COLLECTION_LISTING, COLLECTION_PROMO
from mkt.feed.models import FeedBrand, FeedShelf
from mkt.feed.tests.test_models import FeedAppMixin, FeedTestMixin
from mkt.feed.serializers import (FeedAppSerializer, FeedBrandSerializer,
                                  FeedCollectionSerializer,
                                  FeedShelfSerializer, FeedItemSerializer)
from mkt.regions import RESTOFWORLD


class TestFeedItemSerializer(FeedAppMixin, amo.tests.TestCase):

    def setUp(self):
        super(TestFeedItemSerializer, self).setUp()
        self.create_feedapps()

    def serializer(self, item=None, **context):
        if not item:
            return FeedItemSerializer(context=context)
        return FeedItemSerializer(item, context=context)

    def validate(self, **attrs):
        return self.serializer().validate(attrs=attrs)

    def test_validate_passes(self):
        self.validate(app=self.feedapps[0])

    def test_validate_fails_no_items(self):
        with self.assertRaises(serializers.ValidationError):
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
        with self.assertRaises(serializers.ValidationError):
            self.validate_shelf(region='br')

    def test_validate_shelf_fails_carrier(self):
        with self.assertRaises(serializers.ValidationError):
            self.validate_shelf(carrier='telenor')

    def test_region_handles_worldwide(self):
        data = {
            'region': 'worldwide',
            'item_type': 'app',
            'app': self.feedapps[0].id,
        }
        serializer = FeedItemSerializer(data=data)
        assert serializer.is_valid()
        assert serializer.object.region == RESTOFWORLD.id


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
        serializer = FeedAppSerializer(data=data)
        assert serializer.is_valid()


class TestFeedBrandSerializer(FeedTestMixin, amo.tests.TestCase):

    def setUp(self):
        self.app_ids = [amo.tests.app_factory().id for i in range(3)]
        self.brand = self.feed_brand_factory(app_ids=self.app_ids)
        super(TestFeedBrandSerializer, self).setUp()

    def test_serialization(self):
        data = FeedBrandSerializer(self.brand).data
        eq_(data['slug'], self.brand.slug)
        eq_(data['layout'], self.brand.layout)
        eq_(data['type'], self.brand.type)
        self.assertSetEqual([app['id'] for app in data['apps']], self.app_ids)


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
        return FeedCollectionSerializer().validate_background_color(
            attrs=self.data, source='background_color')

    def test_validate_promo_bg(self):
        self.validate()

    def test_validate_promo_nobg(self):
        del self.data['background_color']
        with self.assertRaises(serializers.ValidationError):
            self.validate()

    def test_validate_listing_bg(self):
        self.data['type'] = COLLECTION_LISTING
        self.validate()

    def test_validate_listing_nobg(self):
        self.data['type'] = COLLECTION_LISTING
        del self.data['background_color']
        self.validate()


class TestFeedShelfSerializer(FeedTestMixin, amo.tests.TestCase):

    def setUp(self):
        self.app_ids = [amo.tests.app_factory().id for i in range(3)]
        self.shelf = self.feed_shelf_factory(app_ids=self.app_ids)
        super(TestFeedShelfSerializer, self).setUp()

    def test_serialization(self):
        data = FeedShelfSerializer(self.shelf).data
        eq_(data['slug'], self.shelf.slug)
        self.assertSetEqual([app['id'] for app in data['apps']], self.app_ids)
