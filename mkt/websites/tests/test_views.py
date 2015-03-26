import json

from django.contrib.auth.models import AnonymousUser
from django.test.client import RequestFactory

from nose.tools import eq_

from mkt.site.tests import ESTestCase
from mkt.websites.models import Website
from mkt.websites.utils import website_factory
from mkt.websites.views import WebsiteSearchView


class TestWebsiteESView(ESTestCase):
    def setUp(self):
        self.website = website_factory()
        super(TestWebsiteESView, self).setUp()
        self._reindex()

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
        response = self._test_get()
        eq_(response.status_code, 200)
        eq_(len(response.json['objects']), 1)
