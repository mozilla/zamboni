import json

from jingo.helpers import urlparams
from mock import patch
from nose import SkipTest
from nose.tools import eq_, ok_

from django.conf import settings
from django.core.urlresolvers import reverse
from django.http import Http404, HttpRequest
from django.test.client import RequestFactory
from django.test.utils import override_settings

import mkt.site.tests
import mkt
from mkt.api.tests.test_oauth import RestOAuth
from mkt.api.views import endpoint_removed, ErrorViewSet
from mkt.site.fixtures import fixture


class TestErrorService(RestOAuth):

    def setUp(self):
        if not settings.ENABLE_API_ERROR_SERVICE:
            # Because this service is activated in urls, you can't reliably
            # test it if the setting is False, because you'd need to force
            # django to re-parse urls before and after the test.
            raise SkipTest()
        super(TestErrorService, self).setUp()
        self.url = reverse('error-list')

    def verify_exception(self, got_request_exception):
        exception_handler_args = got_request_exception.send.call_args
        eq_(exception_handler_args[0][0], ErrorViewSet)
        eq_(exception_handler_args[1]['request'].path, self.url)
        ok_(isinstance(exception_handler_args[1]['request'], HttpRequest))

    @override_settings(DEBUG=False)
    @patch('mkt.api.exceptions.got_request_exception')
    def test_error_service_debug_false(self, got_request_exception):
        res = self.client.get(self.url)
        data = json.loads(res.content)
        eq_(data.keys(), ['detail'])
        eq_(data['detail'], 'Internal Server Error')
        self.verify_exception(got_request_exception)

    @override_settings(DEBUG=True)
    @patch('mkt.api.exceptions.got_request_exception')
    def test_error_service_debug_true(self, got_request_exception):
        res = self.client.get(self.url)
        data = json.loads(res.content)
        eq_(set(data.keys()), set(['detail', 'error_message', 'traceback']))
        eq_(data['detail'], 'Internal Server Error')
        eq_(data['error_message'], 'This is a test.')
        self.verify_exception(got_request_exception)


class TestConfig(RestOAuth):
    fixtures = fixture('user_2519')

    def setUp(self):
        super(TestConfig, self).setUp()
        self.url = reverse('site-config')

    def test_cors(self):
        self.assertCORS(self.anon.get(self.url), 'get')

    def test_switch(self):
        self.create_switch('test-switch', db=True)
        res = self.anon.get(self.url)
        eq_(res.status_code, 200)
        data = json.loads(res.content)

        switch = data['waffle']['switches']['test-switch']
        eq_(switch['name'], 'test-switch')
        eq_(switch['active'], True)

    def test_site_url(self):
        res = self.anon.get(self.url)
        eq_(res.status_code, 200)
        data = json.loads(res.content)
        eq_(data['settings']['SITE_URL'], 'http://testserver')

    def test_no_switch_commonplace(self):
        res = self.client.get(self.url, data={'serializer': 'commonplace'})
        data = json.loads(res.content)
        ok_(not data['waffle']['switches'])

    def test_switch_commonplace(self):
        self.create_switch('eggos', db=True)
        self.create_switch('strudel', db=True)
        res = self.client.get(self.url, data={'serializer': 'commonplace'})
        data = json.loads(res.content)
        self.assertSetEqual(data['waffle']['switches'], ['eggos', 'strudel'])

    def test_fxa(self):
        res = self.client.get(self.url)
        data = json.loads(res.content)
        ok_('fxa' in data)


class TestRegion(RestOAuth):

    def test_list(self):
        res = self.anon.get(urlparams(reverse('regions-list')))
        eq_(res.status_code, 200)
        data = json.loads(res.content)
        for row in data['objects']:
            region = mkt.regions.REGIONS_DICT.get(row['slug'])
            eq_(row['name'], region.name)
            eq_(row['slug'], region.slug)
            eq_(row['id'], region.id)
        eq_(len(data['objects']), len(mkt.regions.REGIONS_DICT))
        eq_(data['meta']['total_count'], len(mkt.regions.REGIONS_DICT))
        eq_(data['objects'][0]['name'], 'Argentina')

    def test_list_translation(self):
        res = self.anon.get(urlparams(reverse('regions-list'), lang='fr'))
        eq_(res.status_code, 200)
        data = json.loads(res.content)
        for row in data['objects']:
            region = mkt.regions.REGIONS_DICT.get(row['slug'])
            eq_(row['name'], region.name)
            eq_(row['slug'], region.slug)
            eq_(row['id'], region.id)
        eq_(len(data['objects']), len(mkt.regions.REGIONS_DICT))
        eq_(data['meta']['total_count'], len(mkt.regions.REGIONS_DICT))
        eq_(data['objects'][0]['name'], 'Afrique du Sud')

    def test_detail(self):
        res = self.get_region('br')
        eq_(res.status_code, 200)
        data = json.loads(res.content)
        region = mkt.regions.REGIONS_DICT['br']
        self.assert_matches_region(data, region)

    def test_detail_worldwide(self):
        res = self.get_region('worldwide')
        eq_(res.status_code, 200)
        data = json.loads(res.content)
        region = mkt.regions.REGIONS_DICT['restofworld']
        self.assert_matches_region(data, region)

    def test_detail_bad_region(self):
        res = self.get_region('foo')
        eq_(res.status_code, 404)

    def assert_matches_region(self, data, region):
        eq_(data['name'], region.name)
        eq_(data['slug'], region.slug)
        eq_(data['id'], region.id)

    def get_region(self, slug):
        return self.anon.get(reverse('regions-detail', kwargs={'pk': slug}))


class TestCarrier(RestOAuth):

    def test_list(self):
        res = self.anon.get(reverse('carriers-list'))
        eq_(res.status_code, 200)
        data = json.loads(res.content)
        for row in data['objects']:
            region = mkt.carriers.CARRIER_MAP.get(row['slug'])
            eq_(row['name'], region.name)
            eq_(row['slug'], region.slug)
            eq_(row['id'], region.id)
        eq_(len(data['objects']), len(mkt.carriers.CARRIER_MAP))
        eq_(data['meta']['total_count'], len(mkt.carriers.CARRIER_MAP))

    def test_detail(self):
        res = self.anon.get(reverse('carriers-detail',
                                    kwargs={'pk': 'carrierless'}))
        eq_(res.status_code, 200)
        data = json.loads(res.content)
        carrier = mkt.carriers.CARRIER_MAP['carrierless']
        eq_(data['name'], carrier.name)
        eq_(data['slug'], carrier.slug)
        eq_(data['id'], carrier.id)


class TestEndpointRemoved(mkt.site.tests.TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_exempt(self):
        ok_(endpoint_removed.csrf_exempt)

    def test_404(self):
        methods = ['get', 'post', 'options']
        for method in methods:
            request = getattr(self.factory, method)('/')
            with self.assertRaises(Http404):
                endpoint_removed(request)
