from urlparse import parse_qs

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseServerError
from django.test.client import RequestFactory
from django.test.utils import override_settings

import mock
from multidb import this_thread_is_pinned
from nose.tools import eq_, ok_

import mkt.site.tests
import mkt.regions
from mkt.api.middleware import (
    APIBaseMiddleware, APIFilterMiddleware, APIPinningMiddleware,
    AuthenticationMiddleware, CORSMiddleware, GZipMiddleware,
    RestOAuthMiddleware)


fireplace_url = 'http://firepla.ce:1234'


class TestCORS(mkt.site.tests.TestCase):

    def setUp(self):
        self.mware = CORSMiddleware()
        self.req = RequestFactory().get('/')
        self.req.API = True

    def test_not_cors(self):
        res = self.mware.process_response(self.req, HttpResponse())
        assert not res.has_header('Access-Control-Allow-Methods')

    def test_cors(self):
        self.req.CORS = ['get']
        res = self.mware.process_response(self.req, HttpResponse())
        eq_(res['Access-Control-Allow-Origin'], '*')
        eq_(res['Access-Control-Allow-Methods'], 'GET, OPTIONS')

    def test_post(self):
        self.req.CORS = ['get', 'post']
        res = self.mware.process_response(self.req, HttpResponse())
        eq_(res['Access-Control-Allow-Methods'], 'GET, POST, OPTIONS')
        eq_(res['Access-Control-Allow-Headers'],
            'X-HTTP-Method-Override, Content-Type')

    def test_custom_request_headers(self):
        self.req.CORS_HEADERS = ['X-Something-Weird', 'Content-Type']
        res = self.mware.process_response(self.req, HttpResponse())
        eq_(res['Access-Control-Allow-Headers'],
            'X-Something-Weird, Content-Type')

    def test_403_get(self):
        resp = HttpResponse()
        resp.status_code = 403

        res = self.mware.process_response(self.req, resp)
        eq_(res['Access-Control-Allow-Origin'], '*')
        eq_(res['Access-Control-Allow-Methods'], 'GET, OPTIONS')

    def test_500_options(self):
        req = RequestFactory().options('/')
        req.API = True
        resp = HttpResponse()
        resp.status_code = 500

        res = self.mware.process_response(req, resp)
        eq_(res['Access-Control-Allow-Origin'], '*')
        eq_(res['Access-Control-Allow-Methods'], 'OPTIONS')

    def test_redirect_madness(self):
        # Because this test is dependent upon the order of middleware in the
        # settings file, this does a full request.
        res = self.client.get('/api/v1/apps/category')
        eq_(res.status_code, 301)
        eq_(res['Access-Control-Allow-Origin'], '*')
        eq_(res['Access-Control-Allow-Methods'], 'GET, OPTIONS')


class TestPinningMiddleware(mkt.site.tests.TestCase):

    def setUp(self):
        self.pin = APIPinningMiddleware()
        self.req = RequestFactory().get('/')
        self.req.API = True
        self.key = 'api-pinning:42'

    def attach_user(self, anon=True):
        self.req.user = mock.Mock(id=42, is_anonymous=lambda: anon)

    def test_pinned_request_method(self):
        self.attach_user(anon=False)

        for method in ['DELETE', 'PATCH', 'POST', 'PUT']:
            self.req.method = method
            self.pin.process_request(self.req)
            ok_(this_thread_is_pinned())

        for method in ['GET', 'HEAD', 'OPTIONS', 'POOP']:
            self.req.method = method
            self.pin.process_request(self.req)
            ok_(not this_thread_is_pinned())

    def test_pinned_cached(self):
        cache.set(self.key, 1, 5)
        self.attach_user(anon=False)
        self.pin.process_request(self.req)
        ok_(this_thread_is_pinned())
        cache.delete(self.key)

    def test_not_pinned(self):
        self.attach_user(anon=True)
        self.pin.process_request(self.req)
        ok_(not this_thread_is_pinned())

    def test_process_response_anon(self):
        self.attach_user(anon=True)
        self.req.method = 'POST'
        self.pin.process_response(self.req, HttpResponse())
        ok_(not cache.get(self.key))

    def test_process_response(self):
        self.attach_user(anon=False)
        for method in ['DELETE', 'PATCH', 'POST', 'PUT']:
            self.req.method = method
            self.pin.process_response(self.req, HttpResponse())
            ok_(cache.get(self.key))
            cache.delete(self.key)

        for method in ['GET', 'HEAD', 'OPTIONS', 'POOP']:
            self.req.method = method
            self.pin.process_response(self.req, HttpResponse())
            ok_(not cache.get(self.key))

    def pinned_header(self):
        self.attach_user(anon=True)
        return self.pin.process_response(
            self.req, HttpResponse())['API-Pinned']

    @mock.patch('mkt.api.middleware.this_thread_is_pinned')
    def test_pinned_header_true(self, mock_pinned):
        mock_pinned.return_value = True
        eq_(self.pinned_header(), 'True')

    @mock.patch('mkt.api.middleware.this_thread_is_pinned')
    def test_pinned_header_false(self, mock_pinned):
        mock_pinned.return_value = False
        eq_(self.pinned_header(), 'False')


@override_settings(API_CURRENT_VERSION=2)
class TestAPIBaseMiddleware(mkt.site.tests.TestCase):

    def setUp(self):
        self.api_version_middleware = APIBaseMiddleware()

    def response(self, url):
        req = RequestFactory().get(url)
        resp = self.api_version_middleware.process_request(req)
        if resp:
            return resp
        return self.api_version_middleware.process_response(
            req, HttpResponse())

    def header(self, res, header):
        return res.get(header, None)

    def test_non_api(self):
        res1 = self.response('/foo/')
        eq_(self.header(res1, 'API-Version'), None)
        eq_(self.header(res1, 'API-Status'), None)

        res2 = self.response('/foo/')
        eq_(self.header(res2, 'API-Version'), None)
        eq_(self.header(res2, 'API-Status'), None)

    def test_version_not_specified(self):
        res = self.response('/api/')
        eq_(self.header(res, 'API-Version'), '1')
        eq_(self.header(res, 'API-Status'), 'Deprecated')

    def test_old_version(self):
        res = self.response('/api/v1/')
        eq_(self.header(res, 'API-Version'), '1')
        eq_(self.header(res, 'API-Status'), 'Deprecated')

    def test_current_version(self):
        res = self.response('/api/v2/')
        eq_(self.header(res, 'API-Version'), '2')
        eq_(self.header(res, 'API-Status'), None)

    def test_future_version(self):
        res = self.response('/api/v3/')
        eq_(self.header(res, 'API-Version'), '3')
        eq_(self.header(res, 'API-Status'), None)

    def test_no_api_version(self):
        req = RequestFactory().get('/api/v2/')
        req.API = True
        res = self.api_version_middleware.process_response(req, HttpResponse())
        eq_(self.header(res, 'API-Version'), '2')
        eq_(self.header(res, 'API-Status'), None)


class TestFilterMiddleware(mkt.site.tests.TestCase):

    def setUp(self):
        self.middleware = APIFilterMiddleware()
        self.factory = RequestFactory()

    def _header(self, url='/', api=True, region=mkt.regions.USA, lang='en-US',
                gaia=True, tablet=True, mobile=True, pro='8a7d546c.32.1',
                response_cls=HttpResponse):
        self.request = self.factory.get(url, {'pro': pro})
        self.request.API = api
        self.request.REGION = region
        self.request.LANG = lang or ''
        self.request.GAIA = gaia
        self.request.TABLET = tablet
        self.request.MOBILE = mobile
        res = self.middleware.process_response(self.request, response_cls())
        if api and response_cls.status_code < 500:
            header = res.get('API-Filter')
            assert 'vary' in res._headers
            eq_(res._headers['vary'][1], 'API-Filter')
            self._test_order(header)
            return parse_qs(header)
        else:
            assert 'vary' not in res._headers
            return None

    def _test_order(self, header):
        order = [item.split('=')[0] for item in header.split('&')]
        eq_(order, sorted(order))

    @mock.patch('mkt.api.middleware.get_carrier')
    def test_success(self, gc):
        carrier = 'telerizon'
        gc.return_value = carrier
        header = self._header()
        self.assertIsInstance(header, dict)
        assert mkt.regions.USA.slug in header['region']
        assert 'en-US' in header['lang']
        assert '8a7d546c.32.1' in header['pro']
        assert carrier in header['carrier']
        self.assertSetEqual(['gaia', 'mobile', 'tablet'], header['device'])

    def test_api_false(self):
        header = self._header(api=False)
        eq_(header, None)

    def test_no_devices(self):
        header = self._header(gaia=False, tablet=False, mobile=False)
        assert 'device' not in header

    def test_one_device(self):
        header = self._header(gaia=True, tablet=False, mobile=False)
        self.assertSetEqual(['gaia'], header['device'])

    @mock.patch('mkt.api.middleware.get_carrier')
    def test_no_carrier(self, gc):
        gc.return_value = None
        header = self._header()
        assert 'carrier' not in header

    def test_region(self):
        region = mkt.regions.BRA
        header = self._header(region=region)
        assert region.slug in header['region']

    def test_no_region(self):
        with self.assertRaises(AttributeError):
            self._header(region=None)

    def test_lang(self):
        lang = 'pt-BR'
        header = self._header(lang=lang)
        assert lang in header['lang']

    def test_no_lang(self):
        header = self._header(lang=None)
        assert 'lang' not in header

    def test_500(self):
        self._header(response_cls=HttpResponseServerError)


class TestGzipMiddleware(mkt.site.tests.TestCase):
    @mock.patch('django.middleware.gzip.GZipMiddleware.process_response')
    def test_enabled_for_api(self, django_gzip_middleware):
        request = mock.Mock()
        request.API = True
        GZipMiddleware().process_response(request, mock.Mock())
        ok_(django_gzip_middleware.called)

    @mock.patch('django.middleware.gzip.GZipMiddleware.process_response')
    def test_disabled_for_the_rest(self, django_gzip_middleware):
        request = mock.Mock()
        request.API = False
        GZipMiddleware().process_response(request, mock.Mock())
        ok_(not django_gzip_middleware.called)

    def test_settings(self):
        # Gzip middleware should be at the top of the list, so that it runs
        # last in the process_response phase, in case the body has been
        # modified by another middleware.
        eq_(settings.MIDDLEWARE_CLASSES[0],
            'mkt.api.middleware.GZipMiddleware')


class TestAuthenticationMiddleware(mkt.site.tests.TestCase):
    @mock.patch('django.contrib.auth.middleware.'
                'AuthenticationMiddleware.process_request')
    def test_does_not_auth_for_api(self, django_authentication_middleware):
        request = mock.Mock()
        request.API = True
        AuthenticationMiddleware().process_request(request)
        ok_(not django_authentication_middleware.called)

    @mock.patch('django.contrib.auth.middleware.'
                'AuthenticationMiddleware.process_request')
    def test_auths_for_non_api(self, django_authentication_middleware):
        request = mock.Mock()
        request.API = False
        AuthenticationMiddleware().process_request(request)
        ok_(django_authentication_middleware.called)

    def test_settings(self):
        # Test that AuthenticationMiddleware comes after
        # APIBaseMiddleware so that request.API is set.
        auth_middleware = 'mkt.api.middleware.AuthenticationMiddleware'
        api_middleware = 'mkt.api.middleware.APIBaseMiddleware'
        index = settings.MIDDLEWARE_CLASSES.index

        ok_(index(auth_middleware) > index(api_middleware))

    @mock.patch('mkt.api.middleware.log')
    def test_shared_secret_no_break_restoauth(self, mock_log):
        shared_secret = 'mkt-shared-secret me@email.com,hash'
        request = RequestFactory(HTTP_AUTHORIZATION=shared_secret).get('/')
        request.API = True
        RestOAuthMiddleware().process_request(request)
        ok_(not mock_log.warning.called)
