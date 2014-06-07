# -*- coding: utf-8 -*-
from datetime import datetime
import json

from django import test
from django.conf import settings

import commonware.log
import mock
from mock import patch
from nose.tools import eq_
from pyquery import PyQuery as pq

import amo.tests
from amo.helpers import absolutify
from amo.urlresolvers import reverse


class Test403(amo.tests.TestCase):
    fixtures = ['base/users']

    def setUp(self):
        assert self.client.login(username='regular@mozilla.com',
                                 password='password')

    def test_403_no_app(self):
        response = self.client.get('/en-US/admin/')
        eq_(response.status_code, 403)
        self.assertTemplateUsed(response, 'amo/403.html')

    def test_403_app(self):
        response = self.client.get('/en-US/thunderbird/admin/', follow=True)
        eq_(response.status_code, 403)
        self.assertTemplateUsed(response, 'amo/403.html')


class Test404(amo.tests.TestCase):

    def test_404_no_app(self):
        """Make sure a 404 without an app doesn't turn into a 500."""
        # That could happen if helpers or templates expect APP to be defined.
        url = reverse('amo.monitor')
        response = self.client.get(url + 'nonsense')
        eq_(response.status_code, 404)
        self.assertTemplateUsed(response, 'amo/404.html')

    def test_404_app_links(self):
        res = self.client.get('/en-US/thunderbird/xxxxxxx')
        eq_(res.status_code, 404)
        self.assertTemplateUsed(res, 'amo/404.html')
        links = pq(res.content)('[role=main] ul a[href^="/en-US/thunderbird"]')
        eq_(links.length, 4)


class TestOtherStuff(amo.tests.TestCase):
    # Tests that don't need fixtures but do need redis mocked.

    def test_language_selector(self):
        doc = pq(test.Client().get('/en-US/firefox/').content)
        eq_(doc('form.languages option[selected]').attr('value'), 'en-us')

    def test_language_selector_variables(self):
        r = self.client.get('/en-US/firefox/?foo=fooval&bar=barval')
        doc = pq(r.content)('form.languages')

        eq_(doc('input[type=hidden][name=foo]').attr('value'), 'fooval')
        eq_(doc('input[type=hidden][name=bar]').attr('value'), 'barval')

    @patch.object(settings, 'KNOWN_PROXIES', ['127.0.0.1'])
    def test_remote_addr(self):
        """Make sure we're setting REMOTE_ADDR from X_FORWARDED_FOR."""
        client = test.Client()
        # Send X-Forwarded-For as it shows up in a wsgi request.
        client.get('/en-US/firefox/', follow=True,
                   HTTP_X_FORWARDED_FOR='1.1.1.1')
        eq_(commonware.log.get_remote_addr(), '1.1.1.1')

    def test_jsi18n_caching(self):
        # The jsi18n catalog should be cached for a long time.
        # Get the url from a real page so it includes the build id.
        client = test.Client()
        doc = pq(client.get('/', follow=True).content)
        js_url = absolutify(reverse('jsi18n'))
        url_with_build = doc('script[src^="%s"]' % js_url).attr('src')

        response = client.get(url_with_build, follow=True)
        fmt = '%a, %d %b %Y %H:%M:%S GMT'
        expires = datetime.strptime(response['Expires'], fmt)
        assert (expires - datetime.now()).days >= 365


@mock.patch('amo.views.log_cef')
class TestCSP(amo.tests.TestCase):

    def setUp(self):
        self.url = reverse('amo.csp.report')
        self.create_sample(name='csp-store-reports')

    def test_get_document(self, log_cef):
        eq_(self.client.get(self.url).status_code, 405)

    def test_malformed(self, log_cef):
        res = self.client.post(self.url, 'f', content_type='application/json')
        eq_(res.status_code, 400)

    def test_document_uri(self, log_cef):
        url = 'http://foo.com'
        self.client.post(self.url,
                         json.dumps({'csp-report': {'document-uri': url}}),
                         content_type='application/json')
        eq_(log_cef.call_args[0][2]['PATH_INFO'], url)

    def test_no_document_uri(self, log_cef):
        self.client.post(self.url, json.dumps({'csp-report': {}}),
                         content_type='application/json')
        eq_(log_cef.call_args[0][2]['PATH_INFO'], '/services/csp/report')
