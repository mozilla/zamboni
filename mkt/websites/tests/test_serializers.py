# -*- coding: utf-8 -*-
from django.contrib.auth.models import AnonymousUser
from django.test.client import RequestFactory

from nose.tools import ok_

import mkt
import mkt.site.tests
from mkt.site.fixtures import fixture
from mkt.users.models import UserProfile
from mkt.websites.indexers import WebsiteIndexer
from mkt.websites.serializers import ESWebsiteSerializer, WebsiteSerializer


class TestWebsiteSerializer(mkt.site.tests.TestCase):
    fixtures = fixture('user_2519')

    def setUp(self):
        self.obj = mkt.site.tests.website_factory(promo_img_hash='abc')
        self.profile = UserProfile.objects.get(pk=2519)
        self.request = RequestFactory().get('/')

    def serialize(self, obj, profile=None):
        self.request.user = profile if profile else AnonymousUser()
        a = WebsiteSerializer(instance=obj, context={'request': self.request})
        return a.data

    def test_promo_imgs(self):
        res = self.serialize(self.obj)
        ok_(res['promo_imgs'][640].endswith('abc'))
        ok_(res['promo_imgs'][1920].endswith('abc'))


class TestESWebsiteSerializer(mkt.site.tests.ESTestCase):
    fixtures = fixture('user_2519',)

    def setUp(self):
        self.profile = UserProfile.objects.get(pk=2519)
        self.request = RequestFactory().get('/')
        self.request.REGION = mkt.regions.USA
        self.request.user = self.profile
        self.obj = mkt.site.tests.website_factory(promo_img_hash='abc')
        self.refresh('website')

    def get_obj(self):
        return WebsiteIndexer.search().filter(
            'term', id=self.obj.pk).execute().hits[0]

    def serialize(self):
        serializer = ESWebsiteSerializer(self.get_obj(),
                                         context={'request': self.request})
        return serializer.data

    def test_promo_img(self):
        res = self.serialize()
        ok_(res['promo_imgs'][640].endswith('abc'))
        ok_(res['promo_imgs'][1920].endswith('abc'))
