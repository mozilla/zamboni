# -*- coding: utf-8 -*-
from nose.tools import eq_
from rest_framework import serializers

import amo
import amo.tests

from mkt.feed.constants import BRAND_LAYOUT_CHOICES, BRAND_TYPE_CHOICES
from mkt.feed.models import FeedBrand
from mkt.feed.serializers import (FeedAppSerializer, FeedBrandSerializer,
                                  FeedItemSerializer)
from mkt.regions import RESTOFWORLD

from .test_views import FeedAppMixin


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

    def test_region_handles_worldwide(self):
        data = {
            'region': 'worldwide',
            'item_type': 'app',
            'app': self.feedapps[0].id,
        }
        serializer = FeedItemSerializer(data=data)
        assert serializer.is_valid()
        assert serializer.object.region == RESTOFWORLD.id


class TestFeedAppSerializer(FeedAppMixin, amo.tests.TestCase):

    def test_basic(self):
        serializer = FeedAppSerializer(data=self.feedapp_data)
        assert serializer.is_valid()


class TestFeedBrandSerializer(amo.tests.TestCase):

    def setUp(self):
        self.brand_data = {
            'slug': 'potato',
            'type': 1,
            'layout': 1
        }
        self.brand = FeedBrand.objects.create(**self.brand_data)
        self.apps = [amo.tests.app_factory() for i in range(3)]
        for app in self.apps:
            self.brand.add_app(app)
        super(TestFeedBrandSerializer, self).setUp()

    def test_serialization(self):
        data = FeedBrandSerializer(self.brand).data
        eq_(data['slug'], self.brand_data['slug'])
        eq_(data['layout'], BRAND_LAYOUT_CHOICES[self.brand_data['layout']][1])
        eq_(data['type'], BRAND_TYPE_CHOICES[self.brand_data['type']][1])
        self.assertSetEqual([app['id'] for app in data['apps']],
                            [app.pk for app in self.apps])

    def test_serialization_validate_layout(self):
        FeedBrandSerializer().validate_layout({'layout': 'grid'}, 'layout')
        with self.assertRaises(serializers.ValidationError):
            FeedBrandSerializer().validate_layout({'layout': 'grdi'}, 'layout')

    def test_serialization_validate_type(self):
        FeedBrandSerializer().validate_type({'type': 'hidden-gem'}, 'type')
        with self.assertRaises(serializers.ValidationError):
            FeedBrandSerializer().validate_type({'type': 'gem'}, 'type')
