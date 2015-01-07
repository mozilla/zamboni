from django.core.urlresolvers import reverse
from django.test.client import RequestFactory

import mock
from nose.tools import eq_

from mkt.site.tests import TestCase
from mkt.carriers import context_processors, get_carrier, set_carrier
from mkt.carriers.middleware import CarrierURLMiddleware


class TestCarrierURLs(TestCase):

    def setUp(self):
        set_carrier(None)

    def request(self, url):
        request = RequestFactory().get(url)
        # Simulate the RequestCookiesMiddleware.
        request.set_cookie = mock.Mock()
        return request

    def get(self, url, request=None):
        if not request:
            request = self.request(url)
        CarrierURLMiddleware().process_request(request)
        return request

    def test_ignore_non_carriers(self):
        request = self.get('/not-a-store')
        eq_(request.path_info, '/not-a-store')
        assert not request.set_cookie.called

    def test_set_carrier(self):
        request = self.get('/?carrier=telefonica')
        eq_(get_carrier(), 'telefonica')
        assert request.set_cookie.called

    def test_set_carrier_none(self):
        request = self.request('/?carrier=')
        request.COOKIES = {'carrier': 'telefonica'}
        request = self.get('/?carrier=', request)
        eq_(get_carrier(), None)
        assert request.set_cookie.called

    def test_set_carrier_to_none_url(self):
        self.get('/telefonica/')
        self.get('/not-a-store')
        eq_(get_carrier(), None)

        self.get('/?carrier=telefonica')
        self.get('/?carrier=not-a-store')
        eq_(get_carrier(), None)

    def test_reverse(self):
        self.get('/telefonica/')
        eq_(reverse('manifest.webapp'), '/manifest.webapp')

        self.get('/?carrier=telefonica')
        eq_(reverse('manifest.webapp'), '/manifest.webapp')

    def test_context(self):
        request = self.get('/?carrier=telefonica')
        eq_(request.path_info, '/')
        ctx = context_processors.carrier_data(request)
        eq_(ctx['CARRIER'], 'telefonica')
