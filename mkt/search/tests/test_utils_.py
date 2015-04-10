from math import log10

from mock import Mock
from nose.tools import eq_

from mkt.constants.base import STATUS_REJECTED
from mkt.site.tests import TestCase
from mkt.site.utils import app_factory
from mkt.search.utils import get_boost, get_popularity, get_trending
from mkt.websites.utils import website_factory


class TestSearchUtils(TestCase):
    def _test_get_trending(self, obj):
        # Test no trending record returns zero.
        eq_(get_trending(obj), 0)

        # Add a region specific trending and test the global one is returned
        # because the region is not mature.
        region = Mock(id=1337, adolescent=True)
        obj.trending.create(value=42.0, region=0)
        obj.trending.create(value=10.0, region=region.id)
        eq_(get_trending(obj, region=region), 42.0)

        # Now test the regional trending is returned when adolescent=False.
        region.adolescent = False
        eq_(get_trending(obj, region=region), 10.0)

    def test_get_trending_app(self):
        app = app_factory()
        self._test_get_trending(app)

    def test_get_trending_website(self):
        website = website_factory()
        self._test_get_trending(website)

    def _test_get_popularity(self, obj):
        # Test no popularity record returns zero.
        eq_(get_trending(obj), 0)

        # Add a region specific popularity and test the global one is returned
        # because the region is not mature.
        region = Mock(id=1337, adolescent=True)
        obj.popularity.create(value=42.0, region=0)
        obj.popularity.create(value=10.0, region=region.id)
        eq_(get_popularity(obj, region=region), 42.0)

        # Now test the regional popularity is returned when adolescent=False.
        region.adolescent = False
        eq_(get_popularity(obj, region=region), 10.0)

    def test_get_popularity_app(self):
        app = app_factory()
        self._test_get_popularity(app)

    def test_get_popularity_website(self):
        website = website_factory()
        self._test_get_popularity(website)

    def test_get_boost_app(self):
        app = app_factory()
        app.popularity.create(region=0, value=1000.0)
        eq_(get_boost(app), log10(1 + 1000) * 4)

    def test_get_boost_app_not_approved(self):
        app = app_factory(status=STATUS_REJECTED)
        app.popularity.create(region=0, value=1000.0)
        eq_(get_boost(app), log10(1 + 1000))

    def test_get_boost_website(self):
        website = website_factory()
        website.popularity.create(region=0, value=1000.0)
        eq_(get_boost(website), log10(1 + 1000) * 4)
