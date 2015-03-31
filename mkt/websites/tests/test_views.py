import json

from django.contrib.auth.models import AnonymousUser
from django.test.client import RequestFactory

from nose.tools import eq_

from mkt.constants.applications import DEVICE_GAIA, DEVICE_DESKTOP
from mkt.constants.regions import BRA, GTM, URY
from mkt.site.tests import ESTestCase, TestCase
from mkt.websites.models import Website
from mkt.websites.utils import website_factory
from mkt.websites.views import WebsiteSearchView, WebsiteView


class TestWebsiteESView(ESTestCase):
    def setUp(self):
        self.website = website_factory(**{
            'categories': json.dumps(['books', 'sports']),
            # This assumes devices and region_exclusions are stored as a json
            # array of ids, not slugs.
            'devices': json.dumps([DEVICE_GAIA.id, DEVICE_DESKTOP.id]),
            'region_exclusions': json.dumps([BRA.id, GTM.id, URY.id]),
        })
        super(TestWebsiteESView, self).setUp()
        self._reindex()

    def tearDown(self):
        Website.get_indexer().unindexer(_all=True)
        super(TestWebsiteESView, self).tearDown()

    def _reindex(self):
        self.reindex(Website, 'mkt_website')

    def _test_get(self):
        # The view is not registered in urls.py at the moment, so we call it
        # and render the response manually instead of letting django do it for
        # us.
        self.req = RequestFactory().get('/')
        self.req.user = AnonymousUser()
        view = WebsiteSearchView.as_view()
        response = view(self.req)
        response.render()
        response.json = json.loads(response.content)
        return response

    def test_basic(self):
        with self.assertNumQueries(0):
            response = self._test_get()
        eq_(response.status_code, 200)
        eq_(len(response.json['objects']), 1)
        data = response.json['objects'][0]
        eq_(data['description'], {'en-US': self.website.description})
        eq_(data['title'], {'en-US': self.website.title})
        eq_(data['short_title'], {'en-US': self.website.short_title})
        eq_(data['url'], {'en-US': self.website.url})
        eq_(data['device_types'], ['firefoxos', 'desktop'])
        eq_(data['categories'], ['books', 'sports'])

    def test_list(self):
        self.website2 = website_factory(url='http://www.lol.com/')
        self._reindex()
        with self.assertNumQueries(0):
            response = self._test_get()
        eq_(response.status_code, 200)
        eq_(len(response.json['objects']), 2)


class TestWebsiteView(TestCase):
    def setUp(self):
        self.website = website_factory(**{
            'categories': json.dumps(['books', 'sports']),
            # This assumes devices and region_exclusions are stored as a json
            # array of ids, not slugs.
            'devices': json.dumps([DEVICE_GAIA.id, DEVICE_DESKTOP.id]),
            'region_exclusions': json.dumps([BRA.id, GTM.id, URY.id]),
        })

    def _test_get(self):
        # The view is not registered in urls.py at the moment, so we call it
        # and render the response manually instead of letting django do it for
        # us.
        self.req = RequestFactory().get('/')
        self.req.user = AnonymousUser()
        view = WebsiteView.as_view()
        response = view(self.req)
        response.render()
        response.json = json.loads(response.content)
        return response

    def test_basic(self):
        response = self._test_get()
        eq_(response.status_code, 200)
        eq_(len(response.json['objects']), 1)
        data = response.json['objects'][0]
        eq_(data['description'], {'en-US': self.website.description})
        eq_(data['title'], {'en-US': self.website.title})
        eq_(data['short_title'], {'en-US': self.website.short_title})
        eq_(data['url'], {'en-US': self.website.url})
        eq_(data['device_types'], ['firefoxos', 'desktop'])
        eq_(data['categories'], ['books', 'sports'])
        # FIXME: regions, keywords

    def test_list(self):
        self.website2 = website_factory()
        response = self._test_get()
        eq_(response.status_code, 200)
        eq_(len(response.json['objects']), 2)
