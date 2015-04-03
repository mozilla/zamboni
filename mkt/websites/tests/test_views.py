import json

from django.contrib.auth.models import AnonymousUser
from django.core.urlresolvers import reverse
from django.test.client import RequestFactory

from nose.tools import eq_

from mkt.api.tests.test_oauth import RestOAuth
from mkt.constants.applications import DEVICE_GAIA, DEVICE_DESKTOP
from mkt.constants.regions import BRA, GTM, URY
from mkt.site.tests import ESTestCase, TestCase
from mkt.websites.models import Website
from mkt.websites.utils import website_factory
from mkt.websites.views import WebsiteView


class TestWebsiteESView(RestOAuth, ESTestCase):
    def setUp(self):
        self.website = website_factory(**{
            'title': 'something',
            'categories': json.dumps(['books', 'sports']),
            # This assumes devices and region_exclusions are stored as a json
            # array of ids, not slugs.
            'devices': json.dumps([DEVICE_GAIA.id, DEVICE_DESKTOP.id]),
            'region_exclusions': json.dumps([BRA.id, GTM.id, URY.id]),
        })
        self.category = 'books'
        self.url = reverse('api-v2:website-search-api')
        super(TestWebsiteESView, self).setUp()
        self._reindex()

    def tearDown(self):
        Website.get_indexer().unindexer(_all=True)
        super(TestWebsiteESView, self).tearDown()

    def _reindex(self):
        self.reindex(Website, 'mkt_website')

    def test_basic(self):
        with self.assertNumQueries(0):
            response = self.anon.get(self.url)
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
            response = self.anon.get(self.url)
        eq_(response.status_code, 200)
        eq_(len(response.json['objects']), 2)

    def test_wrong_category(self):
        res = self.anon.get(self.url, data={'cat': self.category + 'xq'})
        eq_(res.status_code, 400)
        eq_(res['Content-Type'], 'application/json')

    def test_right_category_but_not_present(self):
        self.category = 'travel'
        res = self.anon.get(self.url, data={'cat': self.category})
        eq_(res.status_code, 200)
        eq_(res.json['objects'], [])

    def test_right_category_present(self):
        res = self.anon.get(self.url, data={'cat': self.category})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 1)

    def test_region_filtering(self):
        res = self.anon.get(self.url, data={'region': 'br'})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 0)

        res = self.anon.get(self.url, data={'region': 'es'})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 1)

    def test_q(self):
        res = self.anon.get(self.url, data={'q': 'something'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['id'], self.website.pk)

    def test_q_relevency(self):
        # Add 2 websites - the last one has 'something' appearing in both its
        # title and its description, so it should be booster and appear higher
        # in the results.
        website_factory(title='something')
        boosted_website = website_factory(title='something',
                                          description='something')
        self._reindex()

        res = self.anon.get(self.url, data={'q': 'something'})
        eq_(res.status_code, 200)
        eq_(len(res.json['objects']), 3)
        obj = res.json['objects'][0]
        eq_(obj['id'], boosted_website.pk)

    def test_device_not_present(self):
        res = self.anon.get(
            self.url, data={'dev': 'android', 'device': 'tablet'})
        eq_(res.status_code, 200)
        eq_(res.json['objects'], [])

    def test_device_present(self):
        res = self.anon.get(self.url, data={'dev': 'desktop'})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 1)


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
