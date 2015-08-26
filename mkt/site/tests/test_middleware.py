import datetime

from django.conf import settings
from django.test.utils import override_settings

from dateutil.tz import tzutc
from mock import patch
from nose.tools import eq_, ok_

import mkt.site.tests
from mkt.site.fixtures import fixture
from mkt.site.middleware import lang_from_accept_header
from mkt.users.models import UserProfile


_langs = ['cs', 'de', 'en-US', 'es', 'fr', 'pt-BR', 'pt-PT', 'sr-Latn']


@patch.object(settings, 'LANGUAGES', [x.lower() for x in _langs])
@patch.object(settings, 'LANGUAGE_URL_MAP',
              dict([x.lower(), x] for x in _langs))
class TestLocaleMiddleware(mkt.site.tests.TestCase):

    def test_accept_good_locale(self):
        locales = [
            ('en-US', 'en-US', 'en-US,en-US'),
            ('pt-BR', 'pt-BR', 'pt-BR,en-US'),
            ('pt-br', 'pt-BR', None),
            ('fr', 'fr', 'fr,en-US'),
            ('es-PE', 'es', 'es,en-US'),
            ('fr', 'fr', 'fr,en-US'),
        ]
        for locale, r_lang, c_lang in locales:
            r = self.client.get('/robots.txt?lang=%s' % locale)
            if c_lang:
                eq_(r.cookies['lang'].value, c_lang)
            else:
                eq_(r.cookies.get('lang'), None)
            eq_(r.context['request'].LANG, r_lang)

    def test_accept_language_and_cookies(self):
        # Your cookie tells me pt-BR but your browser tells me en-US.
        self.client.cookies['lang'] = 'pt-BR,pt-BR'
        r = self.client.get('/robots.txt')
        eq_(r.cookies['lang'].value, 'en-US,')
        eq_(r.context['request'].LANG, 'en-US')

        # Your cookie tells me pt-br but your browser tells me en-US.
        self.client.cookies['lang'] = 'pt-br,fr'
        r = self.client.get('/robots.txt')
        eq_(r.cookies['lang'].value, 'en-US,')
        eq_(r.context['request'].LANG, 'en-US')

        # Your cookie tells me pt-BR and your browser tells me pt-BR.
        self.client.cookies['lang'] = 'pt-BR,pt-BR'
        r = self.client.get('/robots.txt', HTTP_ACCEPT_LANGUAGE='pt-BR')
        eq_(r.cookies.get('lang'), None)
        eq_(r.context['request'].LANG, 'pt-BR')

        # You explicitly changed to fr, and your browser still tells me pt-BR.
        # So no new cookie!
        self.client.cookies['lang'] = 'fr,pt-BR'
        r = self.client.get('/robots.txt', HTTP_ACCEPT_LANGUAGE='pt-BR')
        eq_(r.cookies.get('lang'), None)
        eq_(r.context['request'].LANG, 'fr')

        # You explicitly changed to fr, but your browser still tells me es.
        # So make a new cookie!
        self.client.cookies['lang'] = 'fr,pt-BR'
        r = self.client.get('/robots.txt', HTTP_ACCEPT_LANGUAGE='es')
        eq_(r.cookies['lang'].value, 'es,')
        eq_(r.context['request'].LANG, 'es')

    def test_ignore_bad_locale(self):
        # Good? Store language.
        r = self.client.get('/robots.txt?lang=fr')
        eq_(r.cookies['lang'].value, 'fr,en-US')

        # Bad? Reset language.
        r = self.client.get('/robots.txt?lang=')
        eq_(r.cookies['lang'].value, 'en-US,en-US')

        # Still bad? Don't change language.
        for locale in ('xxx', '<script>alert("ballin")</script>'):
            r = self.client.get('/robots.txt?lang=%s' % locale)
            eq_(r.cookies.get('lang'), None)
            eq_(r.context['request'].LANG, settings.LANGUAGE_CODE)

        # Good? Change language.
        r = self.client.get('/robots.txt?lang=fr')
        eq_(r.cookies['lang'].value, 'fr,en-US')

    def test_already_have_cookie_for_bad_locale(self):
        for locale in ('', 'xxx', '<script>alert("ballin")</script>'):
            self.client.cookies['lang'] = locale

            r = self.client.get('/robots.txt')
            eq_(r.cookies['lang'].value, settings.LANGUAGE_CODE + ',')
            eq_(r.context['request'].LANG, settings.LANGUAGE_CODE)

    def test_no_cookie(self):
        r = self.client.get('/robots.txt')
        eq_(r.cookies['lang'].value, settings.LANGUAGE_CODE + ',')
        eq_(r.context['request'].LANG, settings.LANGUAGE_CODE)

    def test_no_api_cookie(self):
        res = self.client.get('/api/v1/apps/schema/?region=restofworld',
                              HTTP_ACCEPT_LANGUAGE='de')
        ok_(not res.cookies)

    def test_cookie_gets_set_once(self):
        r = self.client.get('/robots.txt', HTTP_ACCEPT_LANGUAGE='de')
        eq_(r.cookies['lang'].value, 'de,')

        # Since we already made a request above, we should remember the lang.
        r = self.client.get('/robots.txt', HTTP_ACCEPT_LANGUAGE='de')
        eq_(r.cookies.get('lang'), None)

    def test_accept_language(self):
        locales = [
            ('', settings.LANGUAGE_CODE),
            ('de', 'de'),
            ('en-us, de', 'en-US'),
            ('en-US', 'en-US'),
            ('fr, en', 'fr'),
            ('pt-XX, xx, yy', 'pt-PT'),
            ('pt', 'pt-PT'),
            ('pt, de', 'pt-PT'),
            ('pt-XX, xx, de', 'pt-PT'),
            ('pt-br', 'pt-BR'),
            ('pt-BR', 'pt-BR'),
            ('xx, yy, zz', settings.LANGUAGE_CODE),
            ('<script>alert("ballin")</script>', settings.LANGUAGE_CODE),
            ('en-us;q=0.5, de', 'de'),
            ('es-PE', 'es'),
        ]
        for given, expected in locales:
            r = self.client.get('/robots.txt', HTTP_ACCEPT_LANGUAGE=given)

            got = r.cookies['lang'].value
            eq_(got, expected + ',',
                'For %r: expected %r but got %r' % (given, expected, got))

            got = r.context['request'].LANG
            eq_(got, expected,
                'For %r: expected %r but got %r' % (given, expected, got))

            self.client.cookies.clear()

    def test_accept_language_takes_precedence_over_previous_request(self):
        r = self.client.get('/robots.txt')
        eq_(r.cookies['lang'].value, settings.LANGUAGE_CODE + ',')

        # Even though you remembered my previous language, I've since
        # changed it in my browser, so let's respect that.
        r = self.client.get('/robots.txt', HTTP_ACCEPT_LANGUAGE='fr')
        eq_(r.cookies['lang'].value, 'fr,')

    def test_accept_language_takes_precedence_over_cookie(self):
        self.client.cookies['lang'] = 'pt-BR'

        r = self.client.get('/robots.txt', HTTP_ACCEPT_LANGUAGE='fr')
        eq_(r.cookies['lang'].value, 'fr,')


@patch.object(settings, 'LANGUAGES', [x.lower() for x in _langs])
@patch.object(settings, 'LANGUAGE_URL_MAP',
              dict([x.lower(), x] for x in _langs))
class TestLocaleMiddlewarePersistence(mkt.site.tests.TestCase):
    fixtures = fixture('user_999')

    def test_save_lang(self):
        self.login('regular@mozilla.com')
        self.client.get('/robots.txt', HTTP_ACCEPT_LANGUAGE='sr-Latn')
        eq_(UserProfile.objects.get(pk=999).lang, 'sr-Latn')


class TestVaryMiddleware(mkt.site.tests.TestCase):
    fixtures = fixture('user_999')

    def test_vary_headers(self):
        def vary(res):
            return [x.strip() for x in res.get('Vary', '').split(',')]

        # What is expected to `Vary`.
        res = self.client.get('/developers')
        eq_(sorted(res['Vary'].split(', ')), ['Accept-Language', 'Cookie'])

        res = self.client.get('/developers', follow=True)
        eq_(sorted(res['Vary'].split(', ')), ['Accept-Language', 'Cookie'])

        res = self.client.get('/api/v1/services/config/site/?vary=1')
        # DRF adds `Vary: Accept` by default, so let's not check that.
        assert 'Accept-Language' in vary(res), (
            'Expected "Vary: Accept-Language"')
        assert 'Cookie' in vary(res), 'Expected "Vary: Cookie"'

        res = self.client.get('/api/v1/services/config/site/?vary=0')
        assert 'Accept-Language' not in vary(res), (
            'Should not contain "Vary: Accept-Language"')
        assert 'Cookie' not in vary(res), 'Should not contain "Vary: Cookie"'

    # Patching MIDDLEWARE_CLASSES because other middleware tweaks vary headers.
    @patch.object(settings, 'MIDDLEWARE_CLASSES', [
        'mkt.site.middleware.CommonMiddleware',
        'mkt.site.middleware.NoVarySessionMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
        'mkt.site.middleware.RequestCookiesMiddleware',
        'mkt.site.middleware.LocaleMiddleware',
        'mkt.regions.middleware.RegionMiddleware',
        'mkt.site.middleware.DeviceDetectionMiddleware',
    ])
    def test_no_user_agent(self):
        # We've toggled the middleware to not rewrite the application and also
        # not vary headers based on User-Agent.
        self.login('regular@mozilla.com')

        r = self.client.get('/robots.txt', follow=True)
        eq_(r.status_code, 200)

        assert 'firefox' not in r.request['PATH_INFO'], (
            'Application should not be in the request URL.')
        assert 'User-Agent' not in r['Vary'], (
            'User-Agent should not be in the "Vary" header.')


class TestDeviceMiddleware(mkt.site.tests.TestCase):
    devices = ['mobile', 'gaia']

    def test_no_effect(self):
        r = self.client.get('/robots.txt', follow=True)
        for device in self.devices:
            assert not r.cookies.get(device)
            assert not getattr(r.context['request'], device.upper())

    def test_dev_firefoxos(self):
        req = self.client.get('/robots.txt?dev=firefoxos', follow=True)
        eq_(req.cookies['gaia'].value, 'true')
        assert getattr(req.context['request'], 'GAIA')

    def test_dev_android(self):
        req = self.client.get('/robots.txt?dev=android', follow=True)
        eq_(req.cookies['mobile'].value, 'true')
        assert getattr(req.context['request'], 'MOBILE')

    def test_dev_tablet(self):
        req = self.client.get('/robots.txt?dev=desktop', follow=True)
        eq_(req.cookies['tablet'].value, 'true')
        assert getattr(req.context['request'], 'TABLET')

    def test_force(self):
        for device in self.devices:
            r = self.client.get('/robots.txt?%s=true' % device, follow=True)
            eq_(r.cookies[device].value, 'true')
            assert getattr(r.context['request'], device.upper())

    def test_force_unset(self):
        for device in self.devices:
            r = self.client.get('/robots.txt?%s=true' % device, follow=True)
            assert r.cookies.get(device)

            r = self.client.get('/robots.txt?%s=false' % device, follow=True)
            eq_(r.cookies[device].value, '')
            assert not getattr(r.context['request'], device.upper())

    def test_persists(self):
        for device in self.devices:
            r = self.client.get('/robots.txt?%s=true' % device, follow=True)
            assert r.cookies.get(device)

            r = self.client.get('/robots.txt', follow=True)
            assert getattr(r.context['request'], device.upper())


class TestCacheHeadersMiddleware(mkt.site.tests.TestCase):
    CACHE_DURATION = 60 * 2

    def _test_headers_set(self, res, max_age):
        eq_(res['Cache-Control'],
            'must-revalidate, max-age=%s' % max_age)
        assert res.has_header('ETag'), 'Missing ETag header'

        now = datetime.datetime.now(tzutc())

        self.assertCloseToNow(res['Expires'],
                              now=now + datetime.timedelta(seconds=max_age))
        self.assertCloseToNow(res['Last-Modified'], now=now)

    def _test_headers_missing(self, res):
        assert res.has_header('ETag'), 'Missing ETag header'
        for header in ['Cache-Control', 'Expires', 'Last-Modified']:
            assert not res.has_header(header), (
                'Should not have header: %s: %s' % (header, res[header]))

    @override_settings(CACHE_MIDDLEWARE_SECONDS=CACHE_DURATION, USE_ETAGS=True)
    def test_no_headers_on_disallowed_statuses(self):
        res = self.client.get('/404')  # 404
        self._test_headers_missing(res)

    @override_settings(CACHE_MIDDLEWARE_SECONDS=CACHE_DURATION, USE_ETAGS=True)
    def test_no_headers_on_disallowed_methods(self):
        for method in ('delete', 'post', 'put'):
            res = getattr(self.client, method)('/robots.txt')
            self._test_headers_missing(res)

    @override_settings(CACHE_MIDDLEWARE_SECONDS=CACHE_DURATION, USE_ETAGS=True)
    def test_no_headers_querystring_says_no_cache(self):
        self._test_headers_missing(self.client.get('/robots.txt?cache=0'))

    @override_settings(CACHE_MIDDLEWARE_SECONDS=CACHE_DURATION, USE_ETAGS=True)
    def test_no_headers_querystring_says_garbage(self):
        self._test_headers_missing(self.client.get('/robots.txt?cache=dummy'))

    @override_settings(CACHE_MIDDLEWARE_SECONDS=0, USE_ETAGS=True)
    def test_no_headers_no_querystring(self):
        self._test_headers_missing(self.client.get('/robots.txt'))

    @override_settings(CACHE_MIDDLEWARE_SECONDS=CACHE_DURATION, USE_ETAGS=True)
    def test_headers_set(self):
        for method in ('get', 'head', 'options'):
            res = getattr(self.client, method)('/robots.txt?cache=1')
            self._test_headers_set(res, max_age=self.CACHE_DURATION)

            # We can never get a lower max-age than CACHE_MIDDLEWARE_SECONDS
            # as long as we request caching headers to be set.
            res = getattr(self.client, method)('/robots.txt?cache=60')
            self._test_headers_set(res, max_age=self.CACHE_DURATION)

    @override_settings(CACHE_MIDDLEWARE_SECONDS=CACHE_DURATION, USE_ETAGS=True)
    def test_headers_set_and_long_cache_requested(self):
        for method in ('get', 'head', 'options'):
            res = getattr(self.client, method)('/robots.txt?cache=21600')
            self._test_headers_set(res, max_age=21600)


def accept_check(x, y):
    return eq_(lang_from_accept_header(x), y)


def test_parse_accept_language():
    expected = 'ga-IE', 'zh-TW', 'zh-CN', 'en-US', 'fr'
    for lang in expected:
        assert lang in settings.AMO_LANGUAGES, lang
    d = (('ga-ie', 'ga-IE'),
         # Capitalization is no big deal.
         ('ga-IE', 'ga-IE'),
         ('GA-ie', 'ga-IE'),
         # Go for something less specific.
         ('fr-FR', 'fr'),
         # Go for something more specific.
         ('ga', 'ga-IE'),
         ('ga-XX', 'ga-IE'),
         # With multiple zh-XX choices, choose the first alphabetically.
         ('zh', 'zh-CN'),
         # Default to en-us.
         ('xx', 'en-US'),
         # Check q= sorting.
         ('fr,en;q=0.8', 'fr'),
         ('en;q=0.8,fr,ga-IE;q=0.9', 'fr'),
         # Beware of invalid headers.
         ('en;q=wtf,fr,ga-IE;q=oops', 'en-US'),
         # zh is a partial match but it's still preferred.
         ('zh, fr;q=0.8', 'zh-CN'),
         # Caps + q= sorting.
         ('ga-IE,en;q=0.8,fr;q=0.6', 'ga-IE'),
         ('fr-fr, en;q=0.8, es;q=0.2', 'fr'),
         # Consolidated languages.
         ('es-PE', 'es'),
         )
    for x, y in d:
        yield accept_check, x, y


class TestShorter(mkt.site.tests.TestCase):

    def test_no_shorter_language(self):
        accept_check('zh', 'zh-CN')
        with self.settings(LANGUAGE_URL_MAP={'en-us': 'en-US'}):
            accept_check('zh', 'en-US')
