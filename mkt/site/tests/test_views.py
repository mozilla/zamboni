import json
from urlparse import urljoin

from django.conf import settings
from django.core.urlresolvers import reverse
from django.test.utils import override_settings

import mock
from lxml import etree
from nose.tools import eq_
from pyquery import PyQuery as pq

import mkt.site.tests
from mkt.site.fixtures import fixture
from mkt.webapps.models import Webapp


class Test403(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141', 'users')

    def setUp(self):
        self.login('steamcube@mozilla.com')

    def _test_403(self, url):
        res = self.client.get(url, follow=True)
        eq_(res.status_code, 403)
        self.assertTemplateUsed(res, 'site/403.html')

    def test_403_admin(self):
        self._test_403('/admin')

    def test_403_devhub(self):
        self.login('regular@mozilla.com')
        app = Webapp.objects.get(pk=337141)
        self._test_403(app.get_dev_url('edit'))

    def test_403_reviewer(self):
        self._test_403('/reviewers')


class Test404(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141')

    def _test_404(self, url):
        r = self.client.get(url, follow=True)
        eq_(r.status_code, 404)
        self.assertTemplateUsed(r, 'site/404.html')
        return r

    def test_404(self):
        self._test_404('/xxx')

    def test_404_devhub(self):
        self._test_404('/developers/xxx')

    def test_404_consumer_legacy(self):
        self._test_404('/xxx')

    def test_404_consumer(self):
        self._test_404('/xxx')

    def test_404_api(self):
        res = self.client.get('/api/this-should-never-work/')
        eq_(res.status_code, 404)
        eq_(res.content, '')
        self.assertCORS(res, 'get')

    def test_404_api_debug(self):
        with self.settings(DEBUG=True):
            res = self.client.options('/api/this-should-never-work/')
            eq_(res.status_code, 404)
            self.assertCORS(res)


class TestManifest(mkt.site.tests.TestCase):

    def setUp(self):
        self.url = reverse('manifest.webapp')

    @mock.patch('mkt.carriers.carriers.CARRIERS', {'boop': 'boop'})
    @mock.patch.object(settings, 'WEBAPP_MANIFEST_NAME', 'Firefox Marketplace')
    @mock.patch('mkt.site.views.get_carrier')
    def test_manifest(self, mock_get_carrier):
        mock_get_carrier.return_value = 'boop'
        response = self.client.get(reverse('manifest.webapp'))
        eq_(response.status_code, 200)
        eq_(response['Content-Type'], 'application/x-web-app-manifest+json')
        content = json.loads(response.content)
        eq_(content['name'], 'Firefox Marketplace')
        url = reverse('manifest.webapp')
        assert 'en-US' not in url and 'firefox' not in url
        eq_(content['launch_path'], '/?carrier=boop')

    @mock.patch('mkt.carriers.carriers.CARRIERS', [])
    def test_manifest_no_carrier(self):
        response = self.client.get(self.url)
        eq_(response.status_code, 200)
        content = json.loads(response.content)
        assert 'launch_path' not in content

    @mock.patch.object(settings, 'WEBAPP_MANIFEST_NAME', 'Mozilla Fruitstand')
    def test_manifest_name(self):
        response = self.client.get(self.url)
        eq_(response.status_code, 200)
        content = json.loads(response.content)
        eq_(content['name'], 'Mozilla Fruitstand')

    def test_manifest_etag(self):
        resp = self.client.get(self.url)
        etag = resp.get('Etag')
        assert etag, 'Missing ETag'

        # Trigger a change to the manifest by changing the name.
        with self.settings(WEBAPP_MANIFEST_NAME='Mozilla Fruitstand'):
            resp = self.client.get(self.url)
            assert resp.get('Etag'), 'Missing ETag'
            self.assertNotEqual(etag, resp.get('Etag'))

    def test_conditional_get_manifest(self):
        resp = self.client.get(self.url)
        etag = resp.get('Etag')

        resp = self.client.get(self.url, HTTP_IF_NONE_MATCH=str(etag))
        eq_(resp.content, '')
        eq_(resp.status_code, 304)


class TestRobots(mkt.site.tests.TestCase):

    @override_settings(CARRIER_URLS=['seavanworld'])
    @override_settings(ENGAGE_ROBOTS=True)
    def test_engage_robots(self):
        rs = self.client.get('/robots.txt')
        self.assertContains(rs, 'Allow: /')
        self.assertContains(rs, 'Disallow: /seavanworld/')

    @override_settings(ENGAGE_ROBOTS=False)
    def test_do_not_engage_robots(self):
        rs = self.client.get('/robots.txt')
        self.assertContains(rs, 'Disallow: /')


class TestContribute(mkt.site.tests.TestCase):

    def test_contribute(self):
        response = self.client.get('/contribute.json')
        eq_(response.status_code, 200)
        eq_(response['Content-Type'], 'application/json')
        eq_(json.loads(''.join(response.content)).keys(),
            ['name', 'repository', 'bugs', 'urls', 'participate', 'keywords',
             'description'])


class TestOpensearch(mkt.site.tests.TestCase):

    def test_opensearch_declaration(self):
        """Look for opensearch declaration in templates."""

        response = self.client.get(reverse('commonplace.fireplace'))
        elm = pq(response.content)(
            'link[rel=search][type="application/opensearchdescription+xml"]')
        eq_(elm.attr('href'), reverse('opensearch'))
        eq_(elm.attr('title'), 'Firefox Apps')

    def test_opensearch(self):
        response = self.client.get(reverse('opensearch'))
        eq_(response['Content-Type'], 'text/xml')
        eq_(response.status_code, 200)
        doc = etree.fromstring(response.content)
        e = doc.find('{http://a9.com/-/spec/opensearch/1.1/}ShortName')
        eq_(e.text, 'Firefox Apps')
        e = doc.find('{http://a9.com/-/spec/opensearch/1.1/}Url')
        wanted = '%s?q={searchTerms}' % urljoin(settings.SITE_URL, '/search')
        eq_(e.attrib['template'], wanted)


class TestSecure(mkt.site.tests.TestCase):
    def test_content_nosniff(self):
        # Test that django-secure is properly installed and configured
        # according to our needs.
        response = self.client.get('/')
        eq_(response['x-content-type-options'], 'nosniff')


@mock.patch('mkt.site.views.log_cef')
class TestCSP(mkt.site.tests.TestCase):

    def setUp(self):
        self.url = reverse('mkt.csp.report')
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
