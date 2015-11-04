# -*- coding: utf-8 -*-
import json
from urlparse import urlparse

from django.conf import settings
from django.core.urlresolvers import reverse
from django.http import QueryDict
from django.test.client import RequestFactory

from mock import patch
from nose.tools import eq_, ok_

import mkt
import mkt.regions
from mkt.access.middleware import ACLMiddleware
from mkt.access.models import GroupUser
from mkt.api.tests.test_oauth import RestOAuth, RestOAuthClient
from mkt.constants import regions
from mkt.constants.applications import DEVICE_CHOICES_IDS
from mkt.constants.features import FeatureProfile
from mkt.developers.models import (AddonPaymentAccount, PaymentAccount,
                                   SolitudeSeller)
from mkt.extensions.models import Extension
from mkt.operators.models import OperatorPermission
from mkt.prices.models import Price
from mkt.regions.middleware import RegionMiddleware
from mkt.search.filters import SortingFilter
from mkt.search.forms import COLOMBIA_WEBSITE
from mkt.search.views import SearchView
from mkt.site.fixtures import fixture
from mkt.site.helpers import absolutify
from mkt.site.tests import app_factory, ESTestCase, TestCase, user_factory
from mkt.tags.models import Tag
from mkt.translations.helpers import truncate
from mkt.users.models import UserProfile
from mkt.webapps.indexers import HomescreenIndexer, WebappIndexer
from mkt.webapps.models import AddonDeviceType, AddonUpsell, Webapp
from mkt.webapps.tasks import unindex_webapps
from mkt.websites.models import Website
from mkt.websites.utils import website_factory


class TestGetRegion(TestCase):
    fixtures = fixture('user_2519', 'webapp_337141')

    def setUp(self):
        self.resource = SearchView()
        self.factory = RequestFactory()
        self.profile = UserProfile.objects.get(pk=2519)
        self.user = self.profile
        self.api_version = 1

    def region_for(self, region):
        req = self.factory.get('/', ({} if region is None else
                                     {'region': region}))
        req.API = True
        req.API_VERSION = self.api_version
        req.LANG = ''
        req.user = self.user
        req.user = self.profile
        RegionMiddleware().process_request(req)
        ACLMiddleware().process_request(req)
        return self.resource.get_region_from_request(req)

    @patch('mkt.regions.middleware.RegionMiddleware.region_from_request')
    def test_get_region_all_v1(self, mock_request_region):
        # Different than the default: restofworld.
        geoip_fallback = regions.PER
        mock_request_region.return_value = geoip_fallback

        # Test string values (should return region with that slug).
        eq_(self.region_for('restofworld'), regions.RESTOFWORLD)
        ok_(not mock_request_region.called)

        eq_(self.region_for('us'), regions.USA)
        ok_(not mock_request_region.called)

        # Test fallback to request.REGION (should return GeoIP region if region
        # isn't specified or is specified and empty).
        eq_(self.region_for(None), geoip_fallback)
        eq_(mock_request_region.call_count, 1)

        eq_(self.region_for(''), geoip_fallback)
        eq_(mock_request_region.call_count, 2)

        # Test fallback to restofworld (e.g. if GeoIP fails).
        with patch('mkt.regions.middleware.RegionMiddleware.'
                   'process_request') as mock_process_request:
            eq_(self.region_for(None), regions.RESTOFWORLD)
            ok_(mock_process_request.called)

    @patch('mkt.regions.middleware.RegionMiddleware.region_from_request')
    def test_get_region_all_v2(self, mock_request_region):
        # Different than the default: restofworld.
        geoip_fallback = regions.PER
        mock_request_region.return_value = geoip_fallback

        self.api_version = 2

        # Test string values (should return region with that slug).
        eq_(self.region_for('restofworld'), regions.RESTOFWORLD)
        ok_(not mock_request_region.called)

        eq_(self.region_for('us'), regions.USA)
        ok_(not mock_request_region.called)

        # Test fallback to request.REGION. We are using api v2, so we shouldn't
        # fall back on GeoIP and simply use RESTOFWORLD.
        eq_(self.region_for(None), regions.RESTOFWORLD)
        ok_(not mock_request_region.called)

        eq_(self.region_for(''), regions.RESTOFWORLD)
        ok_(not mock_request_region.called)

    def test_get_region_none(self):
        # When the client explicity requested `region=None` in the query string
        # we should not have a region set at all, not even restofworld.
        eq_(self.region_for('None'), None)

    def test_get_region_worldwide(self):
        eq_(self.region_for('worldwide'), regions.RESTOFWORLD)


@patch('mkt.versions.models.Version.is_privileged', False)
class TestSearchView(RestOAuth, ESTestCase):
    fixtures = fixture('user_2519', 'webapp_337141')

    def setUp(self):
        super(TestSearchView, self).setUp()
        self.url = reverse('search-api')
        self.webapp = Webapp.objects.get(pk=337141)
        self.category = 'books-comics'
        self.webapp.icon_hash = 'fakehash'
        self.webapp.save()
        self.refresh('webapp')

    def tearDown(self):
        for w in Webapp.objects.all():
            w.delete()
        unindex_webapps(list(Webapp.with_deleted.values_list('id', flat=True)))
        super(TestSearchView, self).tearDown()

    def test_verbs(self):
        self._allowed_verbs(self.url, ['get'])

    def test_has_cors(self):
        self.assertCORS(self.anon.get(self.url), 'get')

    def test_meta(self):
        res = self.anon.get(self.url)
        eq_(res.status_code, 200)
        eq_(set(res.json.keys()), set(['objects', 'meta']))
        eq_(res.json['meta']['total_count'], 1)

    @patch('mkt.search.utils.statsd.timer')
    def test_statsd(self, _mock):
        self.anon.get(self.url)
        assert _mock.called

    def test_search_published_apps(self):
        eq_(self.webapp.status, mkt.STATUS_PUBLIC)
        res = self.anon.get(self.url)
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 1)
        eq_(objs[0]['slug'], self.webapp.app_slug)

    def test_search_no_approved_apps(self):
        self.webapp.update(status=mkt.STATUS_APPROVED)
        self.refresh('webapp')
        res = self.anon.get(self.url)
        eq_(res.status_code, 200)
        eq_(res.json['objects'], [])

    def test_search_no_unlisted_apps(self):
        self.webapp.update(status=mkt.STATUS_UNLISTED)
        self.refresh('webapp')
        res = self.anon.get(self.url)
        eq_(res.status_code, 200)
        eq_(res.json['objects'], [])

    def test_wrong_category(self):
        res = self.anon.get(self.url,
                            data={'cat': self.category + 'xq'})
        eq_(res.status_code, 400)
        eq_(res['Content-Type'], 'application/json')

    def test_wrong_sort(self):
        res = self.anon.get(self.url, data={'sort': 'awesomeness'})
        eq_(res.status_code, 400)

    def test_sort(self):
        # Make sure elasticsearch is actually accepting the params.
        for api_sort, es_sort in SortingFilter.DEFAULT_SORTING.items():
            res = self.anon.get(self.url, [('sort', api_sort)])
            eq_(res.status_code, 200, res.content)

    def test_multiple_sort(self):
        res = self.anon.get(self.url, [('sort', 'rating'),
                                       ('sort', 'created')])
        eq_(res.status_code, 200)

    def test_right_category(self):
        res = self.anon.get(self.url, data={'cat': self.category})
        eq_(res.status_code, 200)
        eq_(res.json['objects'], [])

    def create(self):
        self.webapp.update(categories=[self.category])
        self.refresh('webapp')

    def test_right_category_present(self):
        self.create()
        res = self.anon.get(self.url, data={'cat': self.category})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 1)

    def test_old_category(self):
        self.create()
        res = self.anon.get(self.url, data={'cat': 'books'})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 1)

    def test_tarako_category(self):
        self.create()
        # tarako-lifestyle includes books.
        res = self.anon.get(self.url, data={'cat': 'tarako-lifestyle'})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 1)

        # tarako-games includes only games.
        res = self.anon.get(self.url, data={'cat': 'tarako-games'})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 0)

        # tarako-tools includes multiple categories, but not books.
        res = self.anon.get(self.url, data={'cat': 'tarako-tools'})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 0)

    def test_user_info_with_shared_secret(self):
        user = UserProfile.objects.all()[0]

        def fakeauth(auth, req, **kw):
            req.user = user
            req.user = user

        with patch('mkt.api.middleware.RestSharedSecretMiddleware'
                   '.process_request', fakeauth):
            self.create()
            res = self.anon.get(self.url, data={'cat': self.category})
            obj = res.json['objects'][0]
            assert 'user' in obj

    def test_dehydrate(self):
        self.create()
        with self.assertNumQueries(0):
            res = self.anon.get(self.url, data={'cat': self.category})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        content_ratings = obj['content_ratings']
        eq_(obj['absolute_url'],
            absolutify(self.webapp.get_absolute_url()))
        eq_(obj['app_type'], self.webapp.app_type)
        eq_(obj['categories'], [self.category])
        eq_(content_ratings['body'], 'generic')
        eq_(content_ratings['rating'], None)
        eq_(content_ratings['descriptors'], [])
        eq_(content_ratings['interactives'], [])
        eq_(obj['current_version'], u'1.0')
        eq_(obj['description'],
            {'en-US': self.webapp.description.localized_string})
        eq_(obj['icons']['128'], self.webapp.get_icon_url(128))
        ok_(obj['icons']['128'].endswith('?modified=fakehash'))
        eq_(sorted(int(k) for k in obj['icons'].keys()),
            mkt.CONTENT_ICON_SIZES)
        eq_(obj['id'], long(self.webapp.id))
        eq_(obj['is_offline'], False)
        eq_(obj['manifest_url'], self.webapp.get_manifest_url())
        eq_(obj['package_path'], None)
        eq_(obj['payment_account'], None)
        self.assertApiUrlEqual(obj['privacy_policy'],
                               '/apps/app/337141/privacy/')
        eq_(obj['public_stats'], self.webapp.public_stats)
        eq_(obj['ratings'], {'average': 0.0, 'count': 0})
        self.assertApiUrlEqual(obj['resource_uri'],
                               '/apps/app/337141/')
        eq_(obj['slug'], self.webapp.app_slug)
        self.assertSetEqual(obj['supported_locales'],
                            ['en-US', 'es', 'pt-BR'])
        eq_(obj['tags'], [])
        ok_('1.0' in obj['versions'])
        self.assertApiUrlEqual(obj['versions']['1.0'],
                               '/apps/versions/1268829/')

        # These only exists if requested by a reviewer.
        ok_('latest_version' not in obj)
        ok_('reviewer_flags' not in obj)

    @patch('mkt.webapps.models.Webapp.get_excluded_region_ids')
    def test_upsell(self, get_excluded_region_ids):
        get_excluded_region_ids.return_value = []
        upsell = app_factory()
        self.make_premium(upsell)
        AddonUpsell.objects.create(free=self.webapp, premium=upsell)
        self.webapp.save()
        self.refresh('webapp')

        with self.assertNumQueries(0):
            res = self.anon.get(self.url, {'premium_types': 'free'})
        eq_(res.status_code, 200)
        eq_(len(res.json['objects']), 1)
        obj = res.json['objects'][0]
        eq_(obj['upsell']['id'], upsell.id)
        eq_(obj['upsell']['app_slug'], upsell.app_slug)
        eq_(obj['upsell']['name'], upsell.name)
        eq_(obj['upsell']['icon_url'], upsell.get_icon_url(128))
        self.assertApiUrlEqual(obj['upsell']['resource_uri'],
                               '/apps/app/%s/' % upsell.id)
        eq_(obj['upsell']['region_exclusions'], [])

        upsell.delete()
        unindex_webapps([upsell.id])

    def test_dehydrate_regions(self):
        self.webapp.addonexcludedregion.create(region=mkt.regions.BRA.id)
        self.webapp.save()
        self.refresh('webapp')

        res = self.anon.get(self.url)
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        regions = obj['regions']
        ok_(mkt.regions.BRA.slug not in [r['slug'] for r in regions])
        eq_(len(regions), len(mkt.regions.ALL_REGION_IDS) - 1)

    def test_region_filtering(self):
        self.webapp.addonexcludedregion.create(region=mkt.regions.BRA.id)
        self.webapp.save()
        self.refresh('webapp')

        res = self.anon.get(self.url, data={'region': 'br'})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 0)

    def test_languages_filtering(self):
        # This webapp's supported_locales: [u'en-US', u'es', u'pt-BR']

        res = self.anon.get(self.url, data={'languages': 'fr'})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 0)

        for lang in ('fr,pt-BR', 'es, pt-BR', 'es', 'pt-BR'):
            res = self.anon.get(self.url, data={'languages': lang})
            eq_(res.status_code, 200)
            obj = res.json['objects'][0]
            eq_(obj['slug'], self.webapp.app_slug)

    def test_offline_filtering(self):
        def check(offline, visible):
            res = self.anon.get(self.url, data={'offline': offline})
            eq_(res.status_code, 200)
            objs = res.json['objects']
            eq_(len(objs), int(visible))

        # Should NOT show up in offline.
        # Should show up in online.
        # Should show up everywhere if not filtered.
        check(offline='True', visible=False)
        check(offline='False', visible=True)
        check(offline='None', visible=True)

        # Mark that app is capable offline.
        self.webapp.update(is_offline=True)
        self.refresh('webapp')

        # Should show up in offline.
        # Should NOT show up in online.
        # Should show up everywhere if not filtered.
        check(offline='True', visible=True)
        check(offline='False', visible=False)
        check(offline='None', visible=True)

    def test_q(self):
        with self.assertNumQueries(0):
            res = self.anon.get(self.url, data={'q': 'something'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

    def test_q_num_requests(self):
        es = WebappIndexer.get_es()
        orig_search = es.search
        es.counter = 0

        def monkey_search(*args, **kwargs):
            es.counter += 1
            return orig_search(*args, **kwargs)

        es.search = monkey_search

        with self.assertNumQueries(0):
            res = self.anon.get(self.url, data={'q': 'something'})
        eq_(res.status_code, 200)
        eq_(res.json['meta']['total_count'], 1)
        eq_(len(res.json['objects']), 1)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

        # Verify only one search call was made.
        eq_(es.counter, 1)

        es.search = orig_search

    def test_q_num_requests_no_results(self):
        es = WebappIndexer.get_es()
        orig_search = es.search
        es.counter = 0

        def monkey_search(*args, **kwargs):
            es.counter += 1
            return orig_search(*args, **kwargs)

        es.search = monkey_search

        res = self.anon.get(self.url, data={'q': 'noresults'})
        eq_(res.status_code, 200)
        eq_(res.json['meta']['total_count'], 0)
        eq_(len(res.json['objects']), 0)

        # Verify only one search call was made.
        eq_(es.counter, 1)

        es.search = orig_search

    def test_q_exact(self):
        app1 = app_factory(name='test app test11')
        app2 = app_factory(name='test app test21')
        app3 = app_factory(name='test app test31')
        self.refresh('webapp')

        res = self.anon.get(self.url, data={'q': 'test app test21'})
        eq_(res.status_code, 200)
        eq_(len(res.json['objects']), 3)
        # app2 should be first since it's an exact match and is boosted higher.
        obj = res.json['objects'][0]
        eq_(obj['slug'], app2.app_slug)

        app1.delete()
        app2.delete()
        app3.delete()
        unindex_webapps([app1.id, app2.id, app3.id])

    def test_q_is_tag(self):
        Tag(tag_text='whatsupp').save_tag(self.webapp)
        self.webapp.save()
        self.refresh('webapp')
        res = self.anon.get(self.url, data={'q': 'whatsupp'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

    def test_q_is_tag_misspelled(self):
        Tag(tag_text='whatsapp').save_tag(self.webapp)
        self.webapp.save()
        self.refresh('webapp')
        res = self.anon.get(self.url, data={'q': 'whatsupp'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

    def test_fuzzy_match(self):
        res = self.anon.get(self.url, data={'q': 'soemthing'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

    def test_icu_folding(self):
        self.webapp.name = {'es': 'Páginas Amarillos'}
        self.webapp.save()
        self.refresh('webapp')
        res = self.anon.get(self.url, data={'q': 'paginas'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

    def test_camel_case_word_splitting(self):
        self.webapp.name = 'AirCombat'
        self.webapp.save()
        self.refresh('webapp')
        res = self.anon.get(self.url, data={'q': 'air combat'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

    def test_phrase_slop(self):
        self.webapp.name = {'es': 'Metro de Santiago',
                            'en': None}
        self.webapp.save()
        self.refresh('webapp')
        res = self.anon.get(self.url, data={'q': 'metro santiago'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

    def test_phrase_lower(self):
        """
        Phrase queries don't apply analyzers so we want to ensure our code
        lowercases the search query.
        """
        res = self.anon.get(self.url, data={'q': 'Somethin'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

    def test_name_localized(self):
        # First test no ?lang parameter returns all localizations.
        res = self.anon.get(self.url, data={'q': 'something'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)
        eq_(obj['name'], {u'en-US': u'Something Something Steamcube!',
                          u'es': u'Algo Algo Steamcube!'})

        # Second test that adding ?lang returns only that localization.
        res = self.anon.get(self.url,
                            data={'q': 'something', 'lang': 'es'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)
        eq_(obj['name'], u'Algo Algo Steamcube!')

    def test_other_localized(self):
        # Test fields that should be localized.
        translations = {'en-US': u'Test in English',
                        'es': u'Test in Español'}
        self.webapp.homepage = translations
        self.webapp.support_email = translations
        self.webapp.support_url = translations
        self.webapp.save()
        self.refresh('webapp')

        res = self.anon.get(self.url, data={'q': 'something'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['homepage'], translations)
        eq_(obj['support_email'], translations)
        eq_(obj['support_url'], translations)

    def test_name_localized_to_default_locale(self):
        self.webapp.update(default_locale='es')
        self.refresh('webapp')

        # Make a request in another language that we know will fail.
        res = self.anon.get(self.url,
                            data={'q': 'something', 'lang': 'de'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)
        eq_(obj['name'], u'Algo Algo Steamcube!')

    def test_name_localized_exact_match(self):
        other_apps = [app_factory(), app_factory()]
        other_apps[0].name = {'en-US': 'Spanish Tests',
                              'es': 'Pruebas de Español'}
        other_apps[1].name = {'en-US': 'Tests in Spanish',
                              'es': 'Pruebas en Español'}
        for app in other_apps:
            app.save()
        self.refresh('webapp')

        res = self.anon.get(self.url, data={'q': 'Pruebas en Español',
                                            'lang': 'es'})
        eq_(res.status_code, 200)

        # Ensure the exact matched name is first.
        obj = res.json['objects'][0]
        eq_(obj['id'], other_apps[1].id)

        for app in other_apps:
            app.delete()
        unindex_webapps([app.pk for app in other_apps])

    def test_author(self):
        res = self.anon.get(self.url,
                            data={'author': self.webapp.developer_name})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

    def test_author_case(self):
        res = self.anon.get(
            self.url, data={'author': self.webapp.developer_name.upper()})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

    def test_device(self):
        AddonDeviceType.objects.create(
            addon=self.webapp, device_type=DEVICE_CHOICES_IDS['desktop'])
        self.reindex(Webapp)
        res = self.anon.get(self.url, data={'dev': 'desktop'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

    def test_no_flash_on_firefoxos(self):
        AddonDeviceType.objects.create(
            addon=self.webapp, device_type=DEVICE_CHOICES_IDS['firefoxos'])
        f = self.webapp.get_latest_file()
        f.uses_flash = True
        f.save()
        self.reindex(Webapp)
        res = self.anon.get(self.url, data={'dev': 'firefoxos'})
        eq_(res.status_code, 200)
        eq_(len(res.json['objects']), 0)

    def test_premium_types(self):
        with self.assertNumQueries(0):
            res = self.anon.get(self.url, data={'premium_types': 'free'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

    def test_premium_type_premium(self):
        # Make the app paid.
        self.make_premium(self.webapp)
        self.user = UserProfile.objects.get(pk=2519)

        # Prices stuff. This should have happened once before during the life
        # of the worker thread. make_premium() erases that cache so we need to
        # rebuild it to avoid those queries being counted later in the test.
        Price.transformer([])

        # Payment account stuff. We need to create one to avoid useless queries
        # made when we can't find the payment account in Webapp model.
        self.seller = SolitudeSeller.objects.create(
            resource_uri='/path/to/sel', uuid='seller-id', user=self.user)
        self.account = PaymentAccount.objects.create(
            user=self.user, uri='asdf', name='test', inactive=False,
            solitude_seller=self.seller, account_id=123)
        AddonPaymentAccount.objects.create(
            addon=self.webapp, account_uri='foo',
            payment_account=self.account, product_uri='bpruri')

        # Reindex once we have everything.
        self.reindex(Webapp)

        # There should (sadly) be 2 queries: one for the AddonPremium model and
        # price, and one for the AddonPaymentAccount.
        with self.assertNumQueries(2):
            res = self.anon.get(self.url, data={'premium_types': 'premium'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)
        eq_(obj['price'], '1.00')
        eq_(obj['price_locale'], '$1.00')

    def test_premium_types_empty(self):
        with self.assertNumQueries(0):
            res = self.anon.get(self.url, data={'premium_types': 'premium'})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 0)

    def test_multiple_premium_types(self):
        res = self.anon.get(self.url,
                            data={'premium_types': ['free', 'premium']})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

    def test_app_type_hosted(self):
        res = self.anon.get(self.url, data={'app_type': 'hosted'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)
        eq_(obj['is_packaged'], False)
        eq_(obj['package_path'], None)

    def test_app_type_packaged(self):
        self.webapp.update(is_packaged=True)
        f = self.webapp.current_version.all_files[0]

        self.refresh('webapp')

        res = self.anon.get(self.url, data={'app_type': 'packaged'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)
        eq_(obj['is_packaged'], True)
        eq_(obj['package_path'],
            '%s/downloads/file/%s/%s' % (settings.SITE_URL, f.id, f.filename))

    def test_app_type_privileged(self):
        # Override the class-decorated patch.
        with patch('mkt.versions.models.Version.is_privileged', True):
            self.webapp.update(is_packaged=True)
            self.refresh('webapp')

            res = self.anon.get(self.url, data={'app_type': 'packaged'})
            eq_(res.status_code, 200)
            # Packaged also includes privileged, which is technically also a
            # packaged app.
            eq_(len(res.json['objects']), 1)
            obj = res.json['objects'][0]
            eq_(obj['slug'], self.webapp.app_slug)

            res = self.anon.get(self.url,
                                data={'app_type': 'privileged'})
            eq_(res.status_code, 200)
            eq_(len(res.json['objects']), 1)
            obj = res.json['objects'][0]
            eq_(obj['slug'], self.webapp.app_slug)

    def test_installs_allowed_from_anywhere(self):
        res = self.anon.get(self.url, data={'installs_allowed_from': '*'})
        eq_(res.status_code, 200)
        eq_(len(res.json['objects']), 1)

    def test_installs_allowed_from_strict(self):
        self.webapp.current_version.manifest_json.update(
            manifest=json.dumps({'installs_allowed_from': 'http://a.com'}))
        self.reindex(Webapp)
        res = self.anon.get(self.url, data={'installs_allowed_from': '*'})
        eq_(res.status_code, 200)
        eq_(len(res.json['objects']), 0)

    def test_installs_allowed_from_invalid(self):
        res = self.anon.get(
            self.url, data={'installs_allowed_from': 'http://a.com'})
        eq_(res.status_code, 400)
        ok_('installs_allowed_from' in res.json['detail'])

    def test_status_value_packaged(self):
        # When packaged and not a reviewer we exclude latest version status.
        self.webapp.update(is_packaged=True)
        res = self.anon.get(self.url)
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['status'], mkt.STATUS_PUBLIC)
        eq_('latest_version' in obj, False)

    def test_word_delimiter_preserves_original(self):
        self.webapp.description = {
            'en-US': 'This is testing word delimiting preservation in long '
                     'descriptions and here is what we want to find: WhatsApp'
        }
        self.webapp.save()
        self.reindex(Webapp)

        res = self.anon.get(self.url, data={'q': 'whatsapp'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

    def test_pagination(self):
        Webapp.objects.get(pk=337141).delete()
        app1 = app_factory(name='test app test1')
        app2 = app_factory(name='test app test2')
        app3 = app_factory(name='test app test3')
        # Setting 'created' app_factory is unreliable and we need a reliable
        # order.
        app1.update(created=self.days_ago(1))
        app2.update(created=self.days_ago(2))
        app3.update(created=self.days_ago(3))
        self.refresh('webapp')

        res = self.anon.get(self.url, data={'limit': '2', 'sort': 'created'})
        eq_(res.status_code, 200)
        data = json.loads(res.content)
        eq_(len(data['objects']), 2)
        eq_(int(data['objects'][0]['id']), app1.id)
        eq_(int(data['objects'][1]['id']), app2.id)

        eq_(data['meta']['total_count'], 3)
        eq_(data['meta']['limit'], 2)
        eq_(data['meta']['previous'], None)
        eq_(data['meta']['offset'], 0)

        next = urlparse(data['meta']['next'])
        eq_(next.path, self.url)
        eq_(QueryDict(next.query).dict(), {'limit': '2', 'offset': '2',
                                           'sort': 'created'})

        res = self.anon.get(self.url, QueryDict(next.query).dict())
        eq_(res.status_code, 200)
        data = json.loads(res.content)
        eq_(len(data['objects']), 1)
        eq_(int(data['objects'][0]['id']), app3.id)
        eq_(data['meta']['total_count'], 3)
        eq_(data['meta']['limit'], 2)
        prev = urlparse(data['meta']['previous'])
        eq_(next.path, self.url)
        eq_(QueryDict(prev.query).dict(), {'limit': '2', 'offset': '0',
                                           'sort': 'created'})
        eq_(data['meta']['offset'], 2)
        eq_(data['meta']['next'], None)

    def test_pagination_invalid(self):
        res = self.anon.get(self.url, data={'offset': '%E2%98%83'})
        eq_(res.status_code, 200)

    def test_content_ratings_reindex(self):
        self.webapp.set_content_ratings({
            mkt.ratingsbodies.GENERIC: mkt.ratingsbodies.GENERIC_18
        })
        self.refresh('webapp')
        res = self.anon.get(self.url)
        obj = res.json['objects'][0]
        ok_(obj['content_ratings']['rating'])

    def test_usk_refused_exclude(self):
        geodata = self.webapp._geodata
        geodata.update(region_de_usk_exclude=True)
        self.reindex(Webapp)

        res = self.anon.get(self.url, {'region': 'de'})
        ok_(not res.json['objects'])

    def test_icon_url_never(self):
        self.webapp.update(icon_hash=None)
        self.refresh('webapp')
        res = self.anon.get(self.url)
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['icons']['64'], self.webapp.get_icon_url(64))
        ok_(obj['icons']['64'].endswith('?modified=never'))

    def test_tag(self):
        tag1 = Tag.objects.create(tag_text='tagtagtag')
        tag2 = Tag.objects.create(tag_text='tarako')
        Tag.objects.create(tag_text='dummy')
        self.webapp.tags.add(tag1)
        self.webapp.tags.add(tag2)
        self.reindex(Webapp)
        res = self.anon.get(self.url, {'tag': 'tarako'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        self.assertSetEqual(obj['tags'], ['tagtagtag', 'tarako'])

    def test_tag_with_query(self):
        tag1 = Tag.objects.create(tag_text='featured-games')
        tag2 = Tag.objects.create(tag_text='dummy')
        self.webapp.tags.add(tag1)
        self.webapp.tags.add(tag2)
        self.reindex(Webapp)
        res = self.anon.get(self.url, {'q': 'featured-games'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        self.assertSetEqual(obj['tags'], ['featured-games', 'dummy'])

    def test_tag_fuzzy_with_query(self):
        tag1 = Tag.objects.create(tag_text='hairy')
        tag2 = Tag.objects.create(tag_text='dummy')
        self.webapp.tags.add(tag1)
        self.webapp.tags.add(tag2)
        self.reindex(Webapp)
        res = self.anon.get(self.url, {'q': 'hary'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        self.assertSetEqual(obj['tags'], ['hairy', 'dummy'])

    def test_guid(self):
        res = self.anon.get(self.url, {'guid': self.webapp.guid})
        eq_(res.status_code, 200)
        eq_(res.json['objects'][0]['id'], self.webapp.id)

    def test_guid_as_q(self):
        res = self.anon.get(self.url, {'q': self.webapp.guid})
        eq_(res.status_code, 200)
        eq_(res.json['objects'][0]['id'], self.webapp.id)

    def test_ratings_sort(self):
        app1 = self.webapp
        app2 = app_factory()
        user = user_factory()
        app1._reviews.create(user=user, rating=1)
        app2._reviews.create(user=user, rating=5)
        self.refresh('webapp')
        res = self.anon.get(self.url, {'sort': 'rating'})
        eq_(res.status_code, 200)
        eq_(res.json['objects'][0]['id'], app2.id)
        eq_(res.json['objects'][1]['id'], app1.id)

    def test_trending_sort(self):
        app1 = self.webapp
        app2 = app_factory()
        app1.trending.get_or_create(value='2.0')
        app2.trending.get_or_create(value='12.0')
        self.refresh('webapp')
        res = self.anon.get(self.url, {'sort': 'trending'})
        eq_(res.status_code, 200)
        eq_(res.json['objects'][0]['id'], app2.id)
        eq_(res.json['objects'][1]['id'], app1.id)


class TestSearchViewFeatures(RestOAuth, ESTestCase):
    fixtures = fixture('user_2519', 'webapp_337141')

    def setUp(self):
        self.client = RestOAuthClient(None)
        self.url = reverse('search-api')
        self.webapp = Webapp.objects.get(pk=337141)
        self.webapp.addondevicetype_set.create(device_type=mkt.DEVICE_GAIA.id)
        # Pick a few common device features.
        self.features = FeatureProfile(
            apps=True, audio=True, fullscreen=True, geolocation=True,
            indexeddb=True, sms=True)
        self.profile = self.features.to_signature()
        self.qs = {'q': 'something', 'pro': self.profile, 'dev': 'firefoxos'}

    def test_no_features(self):
        # Base test to make sure we find the app.
        self.webapp.save()
        self.refresh('webapp')

        res = self.client.get(self.url, data=self.qs)
        eq_(res.status_code, 200)
        obj = json.loads(res.content)['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

    def test_one_good_feature(self):
        # Enable an app feature that matches one in our profile.
        self.webapp.current_version.features.update(has_geolocation=True)
        self.webapp.save()
        self.refresh('webapp')

        res = self.client.get(self.url, data=self.qs)
        eq_(res.status_code, 200)
        obj = json.loads(res.content)['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

    def test_one_good_feature_base64(self):
        self.profile = self.features.to_base64_signature()
        self.qs['pro'] = self.profile
        self.test_one_good_feature()

    def test_one_bad_feature(self):
        # Enable an app feature that doesn't match one in our profile.
        self.webapp.current_version.features.update(has_pay=True)
        self.webapp.save()
        self.refresh('webapp')

        res = self.client.get(self.url, data=self.qs)
        eq_(res.status_code, 200)
        objs = json.loads(res.content)['objects']
        eq_(len(objs), 0)

    def test_all_good_features(self):
        # Enable app features so they exactly match our device profile.
        self.webapp.current_version.features.update(
            **dict(('has_%s' % k, v) for k, v in self.features.items()))
        self.webapp.save()
        self.refresh('webapp')

        res = self.client.get(self.url, data=self.qs)
        eq_(res.status_code, 200)
        obj = json.loads(res.content)['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

    def test_bad_profile_on_desktop(self):
        # Enable an app feature that doesn't match one in our profile.
        qs = self.qs.copy()
        del qs['dev']  # Desktop doesn't send a device.
        self.webapp.current_version.features.update(has_pay=True)
        self.webapp.save()
        self.refresh('webapp')

        res = self.client.get(self.url, data=qs)
        eq_(res.status_code, 200)
        obj = json.loads(res.content)['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

    @patch('mkt.webapps.models.AppFeatures.to_dict')
    def test_new_unused_feature_doesnt_require_reindex(self, mock_to_dict):
        """Test that we still show apps even when they don't have the latest
        list of features in the index, i.e. that we don't need to reindex apps
        that are not using new features when we add some."""
        # Mock what's returned when we fetch the features to specifically avoid
        # having a value for the "new" feature.
        mock_to_dict.return_value = {}
        self.webapp.save()
        self.refresh('webapp')
        res = self.client.get(self.url, data=self.qs)
        eq_(res.status_code, 200)
        objects = json.loads(res.content)['objects']
        eq_(len(objects), 1)
        obj = objects[0]
        eq_(obj['slug'], self.webapp.app_slug)


class TestFeaturedSearchView(RestOAuth, ESTestCase):
    fixtures = fixture('user_2519', 'webapp_337141')

    def setUp(self):
        super(TestFeaturedSearchView, self).setUp()
        self.url = reverse('featured-search-api')
        self.reindex(Webapp)

    def make_request(self):
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        return res, res.json

    def test_empty_arrays(self):
        """
        Test that when empty arrays for collections, operator and featured keys
        are added for backwards-compatibility in v1.
        """
        res, json = self.make_request()
        eq_(len(res.json['objects']), 1)
        eq_(res.json['collections'], [])
        eq_(res.json['featured'], [])
        eq_(res.json['operator'], [])

    def test_endpoint_removed_v2(self):
        self.url = reverse('api-v2:featured-search-api')
        res = self.client.get(self.url)
        eq_(res.status_code, 404)


class TestSuggestionsView(ESTestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        self.url = reverse('suggestions-search-api')
        self.refresh('webapp')
        self.client = RestOAuthClient(None)
        self.app1 = Webapp.objects.get(pk=337141)
        self.app1.save()
        self.app2 = app_factory(name=u'Second âpp',
                                description=u'Second dèsc' * 25,
                                icon_type='image/png',
                                created=self.days_ago(3))
        self.refresh('webapp')

    def tearDown(self):
        # Cleanup to remove these from the index.
        self.app1.delete()
        self.app2.delete()
        unindex_webapps([self.app1.id, self.app2.id])

    def test_suggestions(self):
        response = self.client.get(self.url, data={'lang': 'en-US'})
        parsed = json.loads(response.content)
        eq_(parsed[0], '')
        self.assertSetEqual(
            parsed[1],
            [unicode(self.app1.name), unicode(self.app2.name)])
        self.assertSetEqual(
            parsed[2],
            [unicode(self.app1.description),
             unicode(truncate(self.app2.description))])
        self.assertSetEqual(
            parsed[3],
            [absolutify(self.app1.get_detail_url()),
             absolutify(self.app2.get_detail_url())])
        self.assertSetEqual(
            parsed[4],
            [self.app1.get_icon_url(64), self.app2.get_icon_url(64)])

    def test_suggestions_filtered(self):
        response = self.client.get(self.url, data={'q': 'Second',
                                                   'lang': 'en-US'})
        parsed = json.loads(response.content)
        eq_(parsed[1], [unicode(self.app2.name)])

    def test_not_finds_invalid_statuses(self):
        for status in [mkt.STATUS_PENDING, mkt.STATUS_APPROVED,
                       mkt.STATUS_UNLISTED, mkt.STATUS_DISABLED,
                       mkt.STATUS_REJECTED, mkt.STATUS_BLOCKED]:
            self.app2.update(status=status)
            self.refresh('webapp')
            res = self.client.get(self.url, data={'q': 'second',
                                                  'lang': 'en-US'})
            eq_(res.status_code, 200)
            eq_(json.loads(res.content)[1], [])

    def test_not_finds_deleted(self):
        self.app2.delete()
        self.refresh('webapp')
        res = self.client.get(self.url, data={'q': 'second',
                                              'lang': 'en-US'})
        eq_(res.status_code, 200)
        eq_(json.loads(res.content)[1], [])


class TestNonPublicSearchView(RestOAuth, ESTestCase):
    fixtures = fixture('user_2519', 'webapp_337141')

    def setUp(self):
        super(TestNonPublicSearchView, self).setUp()
        self.url = reverse('api-v2:non-public-search-api')
        self.refresh('webapp')
        self.app1 = Webapp.objects.get(pk=337141)
        self.app1.save()
        self.app2 = app_factory(name=u'Second âpp',
                                description=u'Second dèsc' * 25,
                                icon_type='image/png',
                                created=self.days_ago(3))
        self.grant_permission(self.profile, 'Feed:Curate')
        self.refresh('webapp')

    def tearDown(self):
        # Cleanup to remove these from the index.
        self.app1.delete()
        self.app2.delete()
        unindex_webapps([self.app1.id, self.app2.id])

    def test_anonymous(self):
        res = self.anon.get(self.url, data={'q': 'second'})
        eq_(res.status_code, 403)

    def test_no_permission(self):
        GroupUser.objects.filter(user=self.profile).delete()
        res = self.client.get(self.url, data={'q': 'second'})
        eq_(res.status_code, 403)

    def test_with_permission(self):
        res = self.client.get(self.url, data={'q': 'second', 'lang': 'en-US'})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 1)
        eq_(objs[0]['name'], self.app2.name)

    def test_finds_valid_statuses(self):
        for status in mkt.VALID_STATUSES:
            self.app2.update(status=status)
            self.refresh('webapp')
            res = self.client.get(self.url, data={'q': 'second',
                                                  'lang': 'en-US'})
            eq_(res.status_code, 200)
            objs = res.json['objects']
            eq_(len(objs), 1)
            eq_(objs[0]['name'], self.app2.name)

    def test_not_finds_invalid_statuses(self):
        for status in [mkt.STATUS_DISABLED, mkt.STATUS_REJECTED,
                       mkt.STATUS_BLOCKED]:
            self.app2.update(status=status)
            self.refresh('webapp')
            res = self.client.get(self.url, data={'q': 'second',
                                                  'lang': 'en-US'})
            eq_(res.status_code, 200)
            eq_(len(res.json['objects']), 0)

    def test_not_finds_deleted(self):
        self.app2.delete()
        self.refresh('webapp')
        res = self.client.get(self.url, data={
            'q': 'second', 'lang': 'en-US', 'region': 'us'
        })
        eq_(res.status_code, 200)
        eq_(len(res.json['objects']), 0)

    def test_not_finds_excluded_region(self):
        self.app2.addonexcludedregion.create(region=mkt.regions.USA.id)
        self.reindex(Webapp)
        res = self.client.get(self.url, data={
            'q': 'second', 'lang': 'en-US', 'region': 'us'
        })
        eq_(res.status_code, 200)
        eq_(len(res.json['objects']), 0)


class TestNoRegionSearchView(RestOAuth, ESTestCase):
    fixtures = fixture('user_2519', 'webapp_337141')

    def setUp(self):
        super(TestNoRegionSearchView, self).setUp()
        self.url = reverse('api-v2:no-region-search-api')
        self.refresh('webapp')
        self.app1 = Webapp.objects.get(pk=337141)
        self.app2 = app_factory(name=u'Second âpp',
                                description=u'Second dèsc' * 25,
                                icon_type='image/png',
                                created=self.days_ago(3))
        # Exclude the app in the region we are going to send. It should not
        # matter.
        self.app2.addonexcludedregion.create(region=mkt.regions.USA.id)
        self.grant_permission(self.profile, 'Feed:Curate')
        self.reindex(Webapp)

    def tearDown(self):
        # Cleanup to remove these from the index.
        self.app1.delete()
        self.app2.delete()
        unindex_webapps([self.app1.id, self.app2.id])

    def test_anonymous(self):
        res = self.anon.get(self.url, data={'q': 'second'})
        eq_(res.status_code, 403)

    def test_no_permission(self):
        GroupUser.objects.filter(user=self.profile).delete()
        res = self.client.get(self.url, data={'q': 'second', 'region': 'us'})
        eq_(res.status_code, 403)

    def test_with_permission(self):
        res = self.client.get(self.url, data={
            'q': 'second', 'lang': 'en-US', 'region': 'us'
        })
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 1)
        eq_(objs[0]['name'], self.app2.name)

    def test_with_operator_permission(self):
        GroupUser.objects.filter(user=self.profile).delete()
        OperatorPermission.objects.create(user=self.profile, carrier=1,
                                          region=8)
        res = self.client.get(self.url, data={
            'q': 'second', 'lang': 'en-US', 'region': 'us'
        })
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 1)
        eq_(objs[0]['name'], self.app2.name)

    def test_not_finds_invalid_statuses(self):
        for status in [mkt.STATUS_PENDING, mkt.STATUS_APPROVED,
                       mkt.STATUS_UNLISTED, mkt.STATUS_DISABLED,
                       mkt.STATUS_REJECTED, mkt.STATUS_BLOCKED]:
            self.app2.update(status=status)
            self.refresh('webapp')
            res = self.client.get(self.url, data={
                'q': 'second', 'lang': 'en-US', 'region': 'us'
            })
            eq_(res.status_code, 200)
            eq_(len(res.json['objects']), 0)

    def test_not_finds_deleted(self):
        self.app2.delete()
        self.refresh('webapp')
        res = self.client.get(self.url, data={
            'q': 'second', 'lang': 'en-US', 'region': 'us'
        })
        eq_(res.status_code, 200)
        eq_(len(res.json['objects']), 0)


class TestRocketbarView(ESTestCase):
    fixtures = fixture('user_2519', 'webapp_337141')

    def setUp(self):
        self.url = reverse('rocketbar-search-api')
        self.refresh('webapp')
        self.client = RestOAuthClient(None)
        self.profile = UserProfile.objects.get(pk=2519)
        self.app1 = Webapp.objects.get(pk=337141)
        self.app1.addondevicetype_set.create(device_type=mkt.DEVICE_GAIA.id)
        self.app1.save()

        self.app2 = app_factory(name=u'Something Second Something Something',
                                description=u'Second dèsc' * 25,
                                icon_type='image/png',
                                icon_hash='fakehash',
                                created=self.days_ago(3),
                                manifest_url='http://rocket.example.com')
        self.app2.addondevicetype_set.create(device_type=mkt.DEVICE_GAIA.id)
        # Add some installs so this app is boosted higher than app1.
        self.app2.popularity.create(region=0, value=1000.0)
        self.app2.save()
        self.refresh('webapp')

    def tearDown(self):
        # Cleanup to remove these from the index.
        self.app1.delete()
        self.app2.delete()
        unindex_webapps([self.app1.id, self.app2.id])
        # Required to purge the suggestions data structure. In Lucene, a
        # document is not deleted from a segment, just marked as deleted.
        WebappIndexer.get_es().indices.optimize(
            index=WebappIndexer.get_index(), only_expunge_deletes=True)

    def test_no_results(self):
        with self.assertNumQueries(0):
            response = self.client.get(self.url, data={'q': 'whatever',
                                                       'lang': 'en-US'})
        parsed = json.loads(response.content)
        eq_(parsed, [])

    def test_suggestions(self):
        with self.assertNumQueries(0):
            response = self.client.get(self.url, data={'q': 'Something Second',
                                                       'lang': 'en-US'})
        parsed = json.loads(response.content)
        eq_(len(parsed), 1)
        eq_(parsed[0], {'manifest_url': self.app2.get_manifest_url(),
                        'icon': self.app2.get_icon_url(64),
                        'name': unicode(self.app2.name),
                        'slug': self.app2.app_slug})
        ok_(self.app2.get_icon_url(64).endswith('?modified=fakehash'))

    def test_suggestion_default_locale(self):
        self.app2.name.locale = 'es'
        self.app2.name.save()
        self.app2.default_locale = 'es'
        self.app2.save()
        self.refresh('webapp')
        with self.assertNumQueries(0):
            response = self.client.get(self.url, data={'q': 'Something Second',
                                                       'lang': 'en-US'})
        parsed = json.loads(response.content)
        eq_(len(parsed), 1)
        eq_(parsed[0], {'manifest_url': self.app2.get_manifest_url(),
                        'icon': self.app2.get_icon_url(64),
                        'name': unicode(self.app2.name),
                        'slug': self.app2.app_slug})

    def test_suggestions_multiple_results(self):
        with self.assertNumQueries(0):
            response = self.client.get(self.url, data={'q': 'Something',
                                                       'lang': 'en-US'})
        parsed = json.loads(response.content)
        eq_(len(parsed), 2)
        # Show app2 first since it gets boosted higher b/c of installs.
        eq_(parsed[0], {'manifest_url': self.app2.get_manifest_url(),
                        'icon': self.app2.get_icon_url(64),
                        'name': unicode(self.app2.name),
                        'slug': self.app2.app_slug})
        eq_(parsed[1], {'manifest_url': self.app1.get_manifest_url(),
                        'icon': self.app1.get_icon_url(64),
                        'name': unicode(self.app1.name),
                        'slug': self.app1.app_slug})

    def test_suggestion_non_gaia_apps(self):
        AddonDeviceType.objects.all().delete()
        self.app1.save()
        self.app2.save()
        self.refresh('webapp')
        with self.assertNumQueries(0):
            response = self.client.get(self.url, data={'q': 'something'})
        parsed = json.loads(response.content)
        eq_(parsed, [])

    def test_suggestions_limit(self):
        with self.assertNumQueries(0):
            response = self.client.get(self.url, data={'q': 'something',
                                                       'lang': 'en-US',
                                                       'limit': 1})
        parsed = json.loads(response.content)
        eq_(len(parsed), 1)
        eq_(parsed[0], {'manifest_url': self.app2.get_manifest_url(),
                        'icon': self.app2.get_icon_url(64),
                        'name': unicode(self.app2.name),
                        'slug': self.app2.app_slug})

    def test_suggestions_with_multiple_icons(self):
        url = reverse('api-v2:rocketbar-search-api')
        with self.assertNumQueries(0):
            response = self.client.get(
                url, data={'q': 'something', 'lang': 'en-US', 'limit': 1})
        parsed = json.loads(response.content)
        eq_(len(parsed), 1)
        eq_(parsed[0]['manifest_url'], self.app2.get_manifest_url())
        eq_(parsed[0]['name'], unicode(self.app2.name))
        eq_(parsed[0]['slug'], self.app2.app_slug)

        assert 'icon' not in parsed[0], '`icon` field has been deprecated.'

        for size in (128, 64, 48, 32):
            eq_(parsed[0]['icons'][str(size)], self.app2.get_icon_url(size))


@patch('mkt.versions.models.Version.is_privileged', False)
class TestMultiSearchView(RestOAuth, ESTestCase):
    fixtures = fixture('user_2519', 'webapp_337141')

    def setUp(self):
        super(TestMultiSearchView, self).setUp()
        self.url = reverse('api-v2:multi-search-api')
        self.webapp = Webapp.objects.get(pk=337141)
        self.webapp.addondevicetype_set.create(device_type=mkt.DEVICE_GAIA.id)
        self.shared_category = 'books-comics'
        self.webapp.update(categories=[self.shared_category, 'business'])
        self.webapp.popularity.create(region=0, value=11.0)
        self.website = website_factory(
            devices=[mkt.DEVICE_GAIA.id],
            name='something something webcube',
            short_name='something',
            title='title something something webcube',
            description={'en-US': 'desc something something webcube',
                         'fr': 'desc something something webcube fr'},
            categories=[self.shared_category, 'sports'],
        )
        self.website.update(last_updated=self.days_ago(1))
        self.extension = Extension.objects.create(
            author='something',
            description={
                'en-US': 'desc something something something webcube',
                'es': 'desc something something something webcube es',
                'fr': 'desc something something something webcube fr'},
            name='something', slug='something')
        self.extension.versions.create(
            reviewed=self.days_ago(0), status=mkt.STATUS_PUBLIC)
        self.refresh(('webapp', 'website', 'extension'))

    def make_homescreen(self):
        self.homescreen = app_factory(name=u'Elegant Waffle',
                                      description=u'homescreen runner',
                                      created=self.days_ago(5),
                                      manifest_url='http://h.testmanifest.com')
        Tag(tag_text='homescreen').save_tag(self.homescreen)
        self.homescreen.addondevicetype_set.create(
            device_type=mkt.DEVICE_GAIA.id)
        self.homescreen.update(categories=['health-fitness', 'productivity'])
        self.homescreen.update_version()
        HomescreenIndexer.index_ids([self.homescreen.pk], no_delay=True)
        self.refresh(('webapp', 'website', 'extension', 'homescreen'))
        return self.homescreen

    def tearDown(self):
        for o in Webapp.objects.all():
            o.delete()
        for o in Website.objects.all():
            o.delete()
        for o in Extension.objects.all():
            o.delete()
        super(TestMultiSearchView, self).tearDown()

        # Make sure to delete and unindex *all* things. Normally we wouldn't
        # care about stray deleted content staying in the index, but they can
        # have an impact on relevancy scoring so we need to make sure. This
        # needs to happen after super() has been called since it'll process the
        # indexing tasks that should happen post_request, and we need to wait
        # for ES to have done everything before continuing.
        Webapp.get_indexer().unindexer(_all=True)
        HomescreenIndexer.unindexer(_all=True)
        Website.get_indexer().unindexer(_all=True)
        Extension.get_indexer().unindexer(_all=True)
        self.refresh(('webapp', 'website', 'extension'))

    def _add_co_tag(self, website):
        co = Tag.objects.get_or_create(tag_text=COLOMBIA_WEBSITE)[0]
        website.keywords.add(co)
        self.reindex(Website)

    def test_verbs(self):
        self._allowed_verbs(self.url, ['get'])

    def test_has_cors(self):
        self.assertCORS(self.anon.get(self.url), 'get')

    def test_meta(self):
        res = self.anon.get(self.url)
        eq_(res.status_code, 200)
        eq_(set(res.json.keys()), set(['objects', 'meta']))
        eq_(res.json['meta']['total_count'], 2)

    @patch('mkt.search.utils.statsd.timer')
    def test_statsd(self, _mock):
        self.anon.get(self.url)
        assert _mock.called

    def test_search_no_doc_type_passed(self):
        self.make_homescreen()
        res = self.anon.get(self.url, data={'lang': 'en-US'})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        # Extensions are excluded by default if there is no doc_type parameter.
        eq_(len(objs), 2)
        eq_(objs[0]['doc_type'], 'webapp')
        eq_(objs[0]['id'], self.webapp.pk)
        eq_(objs[0]['name'], self.webapp.name)
        eq_(objs[0]['slug'], self.webapp.app_slug)
        eq_(objs[1]['doc_type'], 'website')
        eq_(objs[1]['id'], self.website.pk)
        eq_(objs[1]['title'], self.website.title)
        eq_(objs[1]['url'], self.website.url)
        eq_(objs[1]['promo_imgs']['1050'], '')
        eq_(objs[1]['promo_imgs']['640'], '')
        eq_(objs[1]['promo_imgs']['320'], '')

    def test_search_homescreen(self):
        self.make_homescreen()
        res = self.anon.get(self.url, data={'lang': 'en-US',
                                            'doc_type': 'homescreen'})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(objs[0]['id'], self.homescreen.pk)
        eq_(objs[0]['name'], self.homescreen.name)
        eq_(objs[0]['slug'], self.homescreen.app_slug)
        eq_(objs[0]['doc_type'], 'homescreen')

    def test_search_preferred_region_match(self):
        """
        For websites, if the query string is something that will definitely not
        match any websites we may still match on preferred_region. But we don't
        want only preferred_region to find results.
        """
        res = self.anon.get(self.url, data={'q': 'qwertyuiop', 'region': 'uy'})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 0)

    def test_region_explicit_none(self):
        res = self.anon.get(self.url, data={'region': 'None'})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        # Extensions are excluded by default if there is no doc_type parameter.
        eq_(len(objs), 2)

    def test_search_popularity(self):
        self.website.popularity.create(region=0, value=12.0)
        self.extension.popularity.create(region=0, value=42.0)
        # Force reindex to get the new popularity, it's not done automatically.
        self.reindex(Website)
        self.reindex(Extension)
        res = self.anon.get(self.url, data={
            'doc_type': 'extension,webapp,website', 'lang': 'en-US'})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 3)
        eq_(objs[0]['doc_type'], 'extension')
        eq_(objs[0]['id'], self.extension.pk)
        eq_(objs[0]['name'], self.extension.name)
        eq_(objs[0]['slug'], self.extension.slug)
        eq_(objs[1]['doc_type'], 'website')
        eq_(objs[1]['id'], self.website.pk)
        eq_(objs[1]['title'], self.website.title)
        eq_(objs[1]['url'], self.website.url)
        eq_(objs[2]['doc_type'], 'webapp')
        eq_(objs[2]['id'], self.webapp.pk)
        eq_(objs[2]['name'], self.webapp.name)
        eq_(objs[2]['slug'], self.webapp.app_slug)

    def test_search_sort_by_reviewed(self):
        res = self.anon.get(self.url, data={
            'doc_type': 'extension,webapp,website', 'lang': 'en-US',
            'sort': 'reviewed'})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 3)
        eq_(objs[0]['doc_type'], 'extension')
        eq_(objs[0]['id'], self.extension.pk)
        eq_(objs[0]['name'], self.extension.name)
        eq_(objs[0]['slug'], self.extension.slug)
        eq_(objs[1]['doc_type'], 'website')
        eq_(objs[1]['id'], self.website.pk)
        eq_(objs[1]['title'], self.website.title)
        eq_(objs[1]['url'], self.website.url)
        eq_(objs[2]['doc_type'], 'webapp')
        eq_(objs[2]['id'], self.webapp.pk)
        eq_(objs[2]['name'], self.webapp.name)
        eq_(objs[2]['slug'], self.webapp.app_slug)

    def test_search_homescreen_sort_by_reviewed(self):
        self.make_homescreen()
        res = self.anon.get(self.url, data={
            'doc_type': 'extension,webapp,website,homescreen', 'lang': 'en-US',
            'sort': 'reviewed'})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 4)
        eq_(objs[0]['id'], self.extension.pk)
        eq_(objs[1]['id'], self.website.pk)
        eq_(objs[2]['id'], self.webapp.pk)
        eq_(objs[3]['doc_type'], 'homescreen')

    def test_search_q(self):
        res = self.anon.get(self.url, data={
            'doc_type': 'extension,webapp,website', 'lang': 'en-US',
            'q': 'something'})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(res.json['meta']['total_count'], 3)
        # Order should be Extension, Website, Webapp, because the Extension
        # should be more relevant, then the Website, then the Webapp.
        eq_(len(objs), 3)
        eq_(objs[0]['doc_type'], 'extension')
        eq_(objs[0]['id'], self.extension.pk)
        eq_(objs[0]['name'], self.extension.name)
        eq_(objs[0]['slug'], self.extension.slug)
        eq_(objs[1]['doc_type'], 'website')
        eq_(objs[1]['id'], self.website.pk)
        eq_(objs[1]['title'], self.website.title)
        eq_(objs[1]['url'], self.website.url)
        eq_(objs[2]['doc_type'], 'webapp')
        eq_(objs[2]['id'], self.webapp.pk)
        eq_(objs[2]['name'], self.webapp.name)
        eq_(objs[2]['slug'], self.webapp.app_slug)

    def test_search_q_no_doc_type(self):
        res = self.anon.get(self.url, data={'lang': 'en-US', 'q': 'something'})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(res.json['meta']['total_count'], 2)
        # Order should be Website, Webapp, because the Extension is not
        # included and Website should be more relevant than the Webapp.
        eq_(len(objs), 2)
        eq_(objs[0]['doc_type'], 'website')
        eq_(objs[0]['id'], self.website.pk)
        eq_(objs[0]['title'], self.website.title)
        eq_(objs[0]['url'], self.website.url)
        eq_(objs[1]['doc_type'], 'webapp')
        eq_(objs[1]['id'], self.webapp.pk)
        eq_(objs[1]['name'], self.webapp.name)
        eq_(objs[1]['slug'], self.webapp.app_slug)

    def test_site_only(self):
        res = self.anon.get(self.url, data={'q': 'something',
                                            'doc_type': 'website'})
        objs = res.json['objects']
        eq_(res.json['meta']['total_count'], 1)
        eq_(objs[0]['doc_type'], 'website')
        eq_(objs[0]['id'], self.website.pk)

    def test_app_only(self):
        res = self.anon.get(self.url, data={'q': 'something',
                                            'doc_type': 'webapp'})
        objs = res.json['objects']
        eq_(res.json['meta']['total_count'], 1)
        eq_(objs[0]['doc_type'], 'webapp')
        eq_(objs[0]['id'], self.webapp.pk)

    def test_extension_only(self):
        res = self.anon.get(self.url, data={'q': 'something',
                                            'doc_type': 'extension'})
        objs = res.json['objects']
        eq_(res.json['meta']['total_count'], 1)
        eq_(objs[0]['doc_type'], 'extension')
        eq_(objs[0]['id'], self.extension.pk)

    def test_tag_filter_empty(self):
        res = self.anon.get(self.url, data={'tag': 'featured-game'})
        ok_(not res.json['objects'])

    def test_tag_filter_ok(self):
        tag = Tag.objects.create(tag_text='featured-game')
        self.webapp.tags.add(tag)
        self.website.keywords.add(tag)
        self.reindex(Webapp)
        self.reindex(Website)
        self.refresh(('webapp', 'website'))

        res = self.anon.get(self.url, data={'tag': 'featured-game'})
        eq_(res.status_code, 200)
        eq_(len(res.json['objects']), 2)

    def test_colombia(self):
        self._add_co_tag(self.website)
        res = self.client.get(self.url, {'doc_type': 'website',
                                         'region': 'mx'})
        eq_(res.json['meta']['total_count'], 0)
        res_co = self.client.get(self.url, {'doc_type': 'website',
                                            'region': 'co'})
        eq_(res_co.json['meta']['total_count'], 0)

    def test_search_devices(self):
        res = self.client.get(self.url, {
            'dev': 'firefoxos', 'doc_type': 'extension,webapp,website'})
        eq_(res.status_code, 200)
        eq_(res.json['meta']['total_count'], 3)
        eq_(len(res.json['objects']), 3)
        eq_(res.json['objects'][0]['device_types'], ['firefoxos'])
        eq_(res.json['objects'][1]['device_types'], ['firefoxos'])
        eq_(res.json['objects'][2]['device_types'], ['firefoxos'])

    def test_search_typical_full_query(self):
        res = self.client.get(self.url, {
            'dev': 'firefoxos', 'doc_type': 'extension,webapp,website',
            'lang': 'en-US', 'limit': 24, 'q': 'something',
            'pro': '7fffffffffff0.51.6', 'region': 'us'})
        eq_(res.status_code, 200)
        eq_(res.json['meta']['total_count'], 3)
        eq_(len(res.json['objects']), 3)


class TestOpenMobileACLSearchView(RestOAuth, ESTestCase):
    fixtures = fixture('user_2519', 'webapp_337141')

    def setUp(self):
        super(TestOpenMobileACLSearchView, self).setUp()
        self.url = reverse('api-v2:openmobile_acl-search-api')
        self.refresh('webapp')
        self.app1 = Webapp.objects.get(pk=337141)
        # Add an app with openmobile_acl feature enabled. It's unlisted, but
        # we still need it to appear here.
        self.app2 = app_factory(name=u'Second âpp',
                                description=u'Second dèsc' * 25,
                                icon_type='image/png',
                                created=self.days_ago(3),
                                status=mkt.STATUS_UNLISTED)
        self.app2.current_version.features.update(has_openmobileacl=True)
        self.reindex(Webapp)

    def tearDown(self):
        # Cleanup to remove these from the index.
        self.app1.delete()
        self.app2.delete()
        unindex_webapps([self.app1.id, self.app2.id])

    def test_anonymous(self):
        res = self.anon.get(self.url)
        eq_(res.status_code, 200)
        eq_(len(res.json), 1)
        eq_(res.json[0], self.app2.manifest_url)
