from django.contrib.auth.models import AnonymousUser
from django.test.client import RequestFactory

from nose.tools import eq_

from mkt.site.tests import ESTestCase, TestCase, app_factory
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
        eq_(res['tv_featured'], None)

    def test_tv_featured(self):
        self.app.update(tv_featured=3)
        self.refresh('webapp')
        res = self.serialize(self.app)
        eq_(res['tv_featured'], 3)


class AppSerializerTests(AppSerializerTestsMixin, TestCase):
    def refresh(self, _):
        # Only needed for ES tests, so no-op here.
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
        eq_(res['tv_featured'], None)

    def test_tv_featured(self):
        self.website.update(tv_featured=3)
        self.refresh('website')
        res = self.serialize(self.website)
        eq_(res['tv_featured'], 3)


class WebsiteSerializerTests(WebsiteSerializerTestsMixin, TestCase):

    def refresh(self, _):
        # Only needed for ES tests, so no-op here.
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
