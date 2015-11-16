from django.contrib.auth.models import AnonymousUser
from django.test.client import RequestFactory

from nose.tools import ok_

from mkt.site.tests import ESTestCase, TestCase, app_factory
from mkt.tags.models import Tag
from mkt.tvplace.serializers import (TVAppSerializer, TVESAppSerializer,
                                     TVWebsiteSerializer,
                                     TVESWebsiteSerializer)
from mkt.webapps.indexers import WebappIndexer
from mkt.websites.indexers import WebsiteIndexer
from mkt.websites.utils import website_factory


class AppSerializerTestsMixin(object):

    def setUp(self):
        self.creation_date = self.days_ago(1)
        self.app = app_factory()
        self.request = RequestFactory().get('/')
        self.request.user = AnonymousUser()
        self.refresh('webapp')

    def serialize(self, app, profile=None):
        a = TVAppSerializer(instance=app, context={'request': self.request})
        return a.data

    def test_no_tv_featured(self):
        res = self.serialize(self.app)
        ok_(not res['tv_featured'])

    def test_tv_featured(self):
        Tag(tag_text='featured-tv').save_tag(self.app)
        self.app.save()
        self.refresh('webapp')
        res = self.serialize(self.app)
        ok_(res['tv_featured'])


class AppSerializerTests(AppSerializerTestsMixin, TestCase):
    def refresh(self, _):
        pass


class ESAppSerializerTests(AppSerializerTestsMixin, ESTestCase):

    def serialize(self, app, profile=None):
        data = WebappIndexer.search().filter(
            'term', id=app.pk).execute().hits[0]
        a = TVESAppSerializer(instance=data, context={'request': self.request})
        return a.data


class WebsiteSerializerTestsMixin(object):

    def setUp(self):
        self.website = website_factory()
        self.request = RequestFactory().get('/')

    def serialize(self, app, profile=None):
        a = TVWebsiteSerializer(instance=app,
                                context={'request': self.request})
        return a.data

    def test_tv_no_featured(self):
        res = self.serialize(self.website)
        ok_(not res['tv_featured'])

    def test_tv_featured(self):
        Tag(tag_text='featured-tv').save_tag(self.website)
        self.website.save()
        self.refresh('website')
        res = self.serialize(self.website)
        ok_(res['tv_featured'])


class WebsiteSerializerTests(WebsiteSerializerTestsMixin, TestCase):

    def refresh(self, _):
        pass


class ESWebsiteSerializerTests(WebsiteSerializerTestsMixin, ESTestCase):

    def setUp(self):
        super(ESWebsiteSerializerTests, self).setUp()
        self.refresh('website')

    def serialize(self, site, profile=None):
        data = WebsiteIndexer.search().filter(
            'term', id=site.pk).execute().hits[0]
        a = TVESWebsiteSerializer(instance=data,
                                  context={'request': self.request})
        return a.data
