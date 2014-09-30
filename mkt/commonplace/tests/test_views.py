from gzip import GzipFile
from StringIO import StringIO

from django.conf import settings

import mock
from nose import SkipTest
from nose.tools import eq_, ok_
from pyquery import PyQuery as pq

import amo.tests
from amo.utils import reverse


class BaseCommonPlaceTests(amo.tests.TestCase):

    def _test_url(self, url, url_kwargs=None):
        """Test that the given url can be requested, returns a 200, and returns
        a valid gzipped response when requested with Accept-Encoding. Return
        the result of a regular (non-gzipped) request."""
        if not url_kwargs:
            url_kwargs = {}
        res = self.client.get(url, url_kwargs, HTTP_ACCEPT_ENCODING='gzip')
        eq_(res.status_code, 200)
        eq_(res['Content-Encoding'], 'gzip')
        eq_(sorted(res['Vary'].split(', ')),
            ['Accept-Encoding', 'Accept-Language', 'Cookie'])
        ungzipped_content = GzipFile('', 'r', 0, StringIO(res.content)).read()

        res = self.client.get(url, url_kwargs)
        eq_(res.status_code, 200)
        eq_(sorted(res['Vary'].split(', ')),
            ['Accept-Encoding', 'Accept-Language', 'Cookie'])
        eq_(ungzipped_content, res.content)

        return res


class TestCommonplace(BaseCommonPlaceTests):

    def test_fireplace(self):
        res = self._test_url('/server.html')
        self.assertTemplateUsed(res, 'commonplace/index.html')
        self.assertEquals(res.context['repo'], 'fireplace')
        self.assertContains(res, 'splash.css')
        self.assertContains(res, 'login.persona.org/include.js')

    def test_commbadge(self):
        res = self._test_url('/comm/')
        self.assertTemplateUsed(res, 'commonplace/index.html')
        self.assertEquals(res.context['repo'], 'commbadge')
        self.assertNotContains(res, 'splash.css')
        self.assertContains(res, 'login.persona.org/include.js')

    def test_rocketfuel(self):
        res = self._test_url('/curation/')
        self.assertTemplateUsed(res, 'commonplace/index.html')
        self.assertEquals(res.context['repo'], 'rocketfuel')
        self.assertNotContains(res, 'splash.css')
        self.assertContains(res, 'login.persona.org/include.js')

    def test_transonic(self):
        res = self._test_url('/curate/')
        self.assertTemplateUsed(res, 'commonplace/index.html')
        self.assertEquals(res.context['repo'], 'transonic')
        self.assertNotContains(res, 'splash.css')
        self.assertContains(res, 'login.persona.org/include.js')

    def test_discoplace(self):
        res = self._test_url('/discovery/')
        self.assertTemplateUsed(res, 'commonplace/index.html')
        self.assertEquals(res.context['repo'], 'discoplace')
        self.assertContains(res, 'splash.css')
        self.assertNotContains(res, 'login.persona.org/include.js')

    def test_fireplace_persona_js_not_included_on_firefox_os(self):
        for url in ('/server.html?mccs=blah',
                    '/server.html?mcc=blah&mnc=blah',
                    '/server.html?nativepersona=true'):
            res = self._test_url(url)
            self.assertNotContains(res, 'login.persona.org/include.js')

    def test_fireplace_persona_js_not_included_for_firefox_accounts(self):
        self.create_switch('firefox-accounts')
        for url in ('/server.html',
                    '/server.html?mcc=blah',
                    '/server.html?mccs=blah',
                    '/server.html?mcc=blah&mnc=blah',
                    '/server.html?nativepersona=true'):
            res = self._test_url(url)
            self.assertNotContains(res, 'login.persona.org/include.js')

    def test_fireplace_persona_js_is_included_elsewhere(self):
        for url in ('/server.html', '/server.html?mcc=blah'):
            res = self._test_url(url)
            self.assertContains(res, 'login.persona.org/include.js" async')

    def test_rocketfuel_persona_js_is_included(self):
        for url in ('/curation/', '/curation/?nativepersona=true'):
            res = self._test_url(url)
            self.assertContains(res, 'login.persona.org/include.js" defer')


class TestAppcacheManifest(BaseCommonPlaceTests):

    def test_no_repo(self):
        if 'fireplace' not in settings.COMMONPLACE_REPOS_APPCACHED:
            raise SkipTest

        res = self.client.get(reverse('commonplace.appcache'))
        eq_(res.status_code, 404)

    def test_bad_repo(self):
        if 'fireplace' not in settings.COMMONPLACE_REPOS_APPCACHED:
            raise SkipTest

        res = self.client.get(reverse('commonplace.appcache'),
                              {'repo': 'rocketfuel'})
        eq_(res.status_code, 404)

    @mock.patch('mkt.commonplace.views.get_build_id', new=lambda x: 'p00p')
    @mock.patch('mkt.commonplace.views.get_imgurls')
    def test_good_repo(self, get_imgurls_mock):
        if 'fireplace' not in settings.COMMONPLACE_REPOS_APPCACHED:
            raise SkipTest

        img = '/media/img/icons/eggs/h1.gif'
        get_imgurls_mock.return_value = [img]
        res = self._test_url(reverse('commonplace.appcache'),
                             {'repo': 'fireplace'})
        eq_(res.status_code, 200)
        assert '# BUILD_ID p00p' in res.content
        img = img.replace('/media/', '/media/fireplace/')
        assert img + '\n' in res.content


class TestIFrames(BaseCommonPlaceTests):

    def test_basic(self):
        self._test_url(reverse('commonplace.iframe-install'))
        self._test_url(reverse('commonplace.potatolytics'))


class TestOpenGraph(amo.tests.TestCase):

    def _get_tags(self, res):
        """Returns title, image, description."""
        doc = pq(res.content)
        return (doc('[property="og:title"]').attr('content'),
                doc('[property="og:image"]').attr('content'),
                doc('[name="description"]').attr('content'))

    def test_basic(self):
        res = self.client.get(reverse('commonplace.fireplace'))
        title, image, description = self._get_tags(res)
        eq_(title, 'Firefox Marketplace')
        ok_(description.startswith('The Firefox Marketplace is'))

    def test_detail(self):
        app = amo.tests.app_factory(description='Awesome')
        res = self.client.get(reverse('detail', args=[app.app_slug]))
        title, image, description = self._get_tags(res)
        eq_(title, app.name)
        eq_(image, app.get_icon_url(64))
        eq_(description, app.description)

    def test_detail_dne(self):
        res = self.client.get(reverse('detail', args=['DO NOT EXISTS']))
        title, image, description = self._get_tags(res)
        eq_(title, 'Firefox Marketplace')
        ok_(description.startswith('The Firefox Marketplace is'))


class TestOpenGraph(amo.tests.TestCase):

    def _get_tags(self, res):
        """Returns title, image, description."""
        doc = pq(res.content)
        return (doc('[property="og:title"]').attr('content'),
                doc('[property="og:image"]').attr('content'),
                doc('[name="description"]').attr('content'))

    def test_basic(self):
        res = self.client.get(reverse('commonplace.fireplace'))
        title, image, description = self._get_tags(res)
        eq_(title, 'Firefox Marketplace')
        ok_(description.startswith('The Firefox Marketplace is'))

    def test_detail(self):
        app = amo.tests.app_factory(description='Awesome')
        res = self.client.get(reverse('detail', args=[app.app_slug]))
        title, image, description = self._get_tags(res)
        eq_(title, app.name)
        eq_(image, app.get_icon_url(64))
        eq_(description, app.description)

    def test_detail_dne(self):
        res = self.client.get(reverse('detail', args=['DO NOT EXISTS']))
        title, image, description = self._get_tags(res)
        eq_(title, 'Firefox Marketplace')
        ok_(description.startswith('The Firefox Marketplace is'))

    def test_description_safe_escape(self):
        app = amo.tests.app_factory(
            description='><script>alert();</script>')
        res = self.client.get(reverse('detail', args=[app.app_slug]))
        title, image, description = self._get_tags(res)
        eq_(description, '><script>alert();</script>')
