import json

from django.core.cache import cache

from mock import patch
from nose.tools import eq_, ok_

from mkt.langpacks.models import LangPack
from mkt.site.fixtures import fixture
from mkt.site.tests import TestCase
from mkt.webapps.models import Webapp
from mkt.webapps.utils import get_cached_minifest, get_supported_locales


class TestSupportedLocales(TestCase):

    def setUp(self):
        self.manifest = {'default_locale': 'en'}

    def check(self, expected):
        eq_(get_supported_locales(self.manifest), expected)

    def test_empty_locale(self):
        self.check([])

    def test_single_locale(self):
        self.manifest.update({'locales': {'es': {'name': 'eso'}}})
        self.check(['es'])

    def test_multiple_locales(self):
        self.manifest.update({'locales': {'es': {'name': 'si'},
                                          'fr': {'name': 'oui'}}})
        self.check(['es', 'fr'])

    def test_short_locale(self):
        self.manifest.update({'locales': {'pt': {'name': 'sim'}}})
        self.check(['pt-PT'])

    def test_unsupported_locale(self):
        self.manifest.update({'locales': {'xx': {'name': 'xx'}}})
        self.check([])


class TestCachedMinifest(TestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        self.webapp = Webapp.objects.get(pk=337141)

    @patch('mkt.webapps.utils.storage')
    def test_get_cached_minifest_caching_force(self, storage_mock):
        storage_mock.size.return_value = 999
        minifest = json.loads(get_cached_minifest(self.webapp))
        eq_(minifest['size'], 999)

        # Change the size, the minifest should be updated because we are
        # passing force=True.
        storage_mock.size.return_value = 666
        new_minifest = json.loads(get_cached_minifest(self.webapp, force=True))
        ok_(new_minifest != minifest)
        eq_(new_minifest['size'], 666)

    @patch('mkt.webapps.utils.storage')
    def test_get_cached_minifest_caching(self, storage_mock):
        storage_mock.size.return_value = 999
        minifest = json.loads(get_cached_minifest(self.webapp))
        eq_(minifest['size'], 999)

        # Change the size, the minifest should stay the same thanks to caching.
        storage_mock.size.return_value = 666
        new_minifest = json.loads(get_cached_minifest(self.webapp))
        eq_(new_minifest, minifest)

    @patch('mkt.webapps.utils.storage')
    def test_caching_key_differs_between_models(self, storage_mock):
        storage_mock.size.return_value = 999

        ok_(not cache.get('webapp:337141:manifest'))
        get_cached_minifest(self.webapp)

        ok_(not cache.get(
            'langpack:12345678123456781234567812345678:manifest'))
        langpack = LangPack(pk='12345678123456781234567812345678',
                            manifest='{}')
        get_cached_minifest(langpack)

        ok_(cache.get('webapp:337141:manifest'))
        ok_(cache.get('langpack:12345678123456781234567812345678:manifest'))
