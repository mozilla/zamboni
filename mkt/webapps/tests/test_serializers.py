# -*- coding: utf-8 -*-
from decimal import Decimal

from django.contrib.auth.models import AnonymousUser
from django.core.urlresolvers import reverse
from django.test.client import RequestFactory
from django.test.utils import override_settings

import mock
from nose.tools import eq_, ok_

import mkt
import mkt.site.tests
from mkt.constants import ratingsbodies, regions
from mkt.constants.payments import PROVIDER_REFERENCE
from mkt.constants.regions import RESTOFWORLD
from mkt.developers.models import (AddonPaymentAccount, PaymentAccount,
                                   SolitudeSeller)
from mkt.prices.models import PriceCurrency
from mkt.regions.middleware import RegionMiddleware
from mkt.site.fixtures import fixture
from mkt.users.models import UserProfile
from mkt.versions.models import Version
from mkt.webapps.indexers import WebappIndexer
from mkt.webapps.models import AddonDeviceType, Installed, Preview, Webapp
from mkt.webapps.serializers import (AppSerializer, ESAppSerializer,
                                     SimpleESAppSerializer)


class TestAppSerializer(mkt.site.tests.TestCase):
    fixtures = fixture('user_2519')

    def setUp(self):
        self.creation_date = self.days_ago(1)
        self.app = mkt.site.tests.app_factory(
            version_kw={'version': '1.8'}, created=self.creation_date)
        self.profile = UserProfile.objects.get(pk=2519)
        self.request = RequestFactory().get('/')

    def serialize(self, app, profile=None):
        self.request.user = profile if profile else AnonymousUser()
        a = AppSerializer(instance=app, context={'request': self.request})
        return a.data

    def test_base(self):
        res = self.serialize(self.app)
        self.assertCloseToNow(res['last_updated'], now=self.app.last_updated)

    def test_packaged(self):
        res = self.serialize(self.app)
        eq_(res['is_packaged'], False)
        eq_(res['is_offline'], False)

        self.app.update(is_packaged=True, is_offline=True)

        res = self.serialize(self.app)
        eq_(res['is_packaged'], True)
        eq_(res['is_offline'], True)

    @override_settings(SITE_URL='http://hy.fr')
    def test_package_path(self):
        res = self.serialize(self.app)
        eq_(res['package_path'], None)

        self.app.update(is_packaged=True)
        res = self.serialize(self.app)

        pkg = self.app.versions.latest().files.latest()
        eq_(res['package_path'], self.app.get_package_path())

        # This method is already tested in `mkt.webapps.tests.test_models`,
        # but let's test it anyway.
        eq_(res['package_path'],
            'http://hy.fr/downloads/file/%s/%s' % (pkg.id, pkg.filename))

    def test_no_previews(self):
        eq_(self.serialize(self.app)['previews'], [])

    def test_with_preview(self):
        obj = Preview.objects.create(**{
            'filetype': 'image/png', 'thumbtype': 'image/png',
            'addon': self.app})
        preview = self.serialize(self.app)['previews'][0]
        self.assertSetEqual(preview, ['filetype', 'id', 'image_url',
                                      'thumbnail_url', 'resource_uri'])
        eq_(int(preview['id']), obj.pk)

    def test_no_rating(self):
        eq_(self.serialize(self.app)['content_ratings']['rating'], None)

    def test_no_price(self):
        res = self.serialize(self.app)
        eq_(res['price'], None)
        eq_(res['price_locale'], None)
        eq_(res['payment_required'], False)

    def check_profile(self, profile, **kw):
        expected = {'developed': False, 'installed': False, 'purchased': False}
        expected.update(**kw)
        eq_(profile, expected)

    def test_installed(self):
        self.app.installed.create(user=self.profile)
        res = self.serialize(self.app, profile=self.profile)
        self.check_profile(res['user'], installed=True)

    def test_purchased(self):
        self.app.addonpurchase_set.create(user=self.profile)
        res = self.serialize(self.app, profile=self.profile)
        self.check_profile(res['user'], purchased=True)

    def test_owned(self):
        self.app.addonuser_set.create(user=self.profile)
        res = self.serialize(self.app, profile=self.profile)
        self.check_profile(res['user'], developed=True)

    def test_locales(self):
        res = self.serialize(self.app)
        eq_(res['default_locale'], 'en-US')
        eq_(res['supported_locales'], [])

    def test_multiple_locales(self):
        self.app.current_version.update(supported_locales='en-US,it')
        res = self.serialize(self.app)
        self.assertSetEqual(res['supported_locales'], ['en-US', 'it'])

    def test_regions(self):
        res = self.serialize(self.app)
        self.assertSetEqual([region['slug'] for region in res['regions']],
                            [region.slug for region in self.app.get_regions()])

    def test_current_version(self):
        res = self.serialize(self.app)
        ok_('current_version' in res)
        eq_(res['current_version'], self.app.current_version.version)

    def test_versions_one(self):
        res = self.serialize(self.app)
        self.assertSetEqual([v.version for v in self.app.versions.all()],
                            res['versions'].keys())

    def test_versions_multiple(self):
        ver = Version.objects.create(addon=self.app, version='1.9')
        self.app.update(_current_version=ver, _latest_version=ver)
        res = self.serialize(self.app)
        eq_(res['current_version'], ver.version)
        self.assertSetEqual([v.version for v in self.app.versions.all()],
                            res['versions'].keys())

    def test_categories(self):
        self.app.update(categories=['books', 'social'])
        res = self.serialize(self.app)
        self.assertSetEqual(res['categories'], ['books', 'social'])

    def test_content_ratings(self):
        self.app.set_content_ratings({
            ratingsbodies.CLASSIND: ratingsbodies.CLASSIND_18,
            ratingsbodies.GENERIC: ratingsbodies.GENERIC_18,
        })

        res = self.serialize(self.app)
        eq_(res['content_ratings']['body'], 'generic')
        eq_(res['content_ratings']['rating'], '18')

        self.request.REGION = mkt.regions.BRA
        res = self.serialize(self.app)
        eq_(res['content_ratings']['body'], 'classind')
        eq_(res['content_ratings']['rating'], '18')

    def test_content_descriptors(self):
        self.app.set_descriptors(['has_esrb_blood', 'has_esrb_crime',
                                  'has_pegi_scary'])

        self.request.REGION = mkt.regions.USA
        res = self.serialize(self.app)
        self.assertSetEqual(res['content_ratings']['descriptors_text'],
                            ['Blood', 'Crime'])
        self.assertSetEqual(res['content_ratings']['descriptors'],
                            ['has_esrb_blood', 'has_esrb_crime'])

    def test_interactive_elements(self):
        self.app.set_interactives(['has_digital_purchases', 'has_shares_info'])
        res = self.serialize(self.app)
        eq_(
            res['content_ratings']['interactives_text'],
            ['Digital Purchases', 'Shares Info'])
        eq_(
            res['content_ratings']['interactives'],
            ['has_digital_purchases', 'has_shares_info'])

    def test_no_release_notes(self):
        res = self.serialize(self.app)
        eq_(res['release_notes'], None)

        self.app.current_version.delete()
        self.app.update_version()
        eq_(self.app.current_version, None)
        res = self.serialize(self.app)
        eq_(res['release_notes'], None)

    def test_release_notes(self):
        version = self.app.current_version
        version.releasenotes = u'These are nötes.'
        version.save()
        res = self.serialize(self.app)
        eq_(res['release_notes'], {u'en-US': unicode(version.releasenotes)})

        self.request = RequestFactory().get('/?lang=whatever')
        res = self.serialize(self.app)
        eq_(res['release_notes'], unicode(version.releasenotes))

    def test_file_size(self):
        f = self.app.current_version.all_files[0]
        f.update(size=12345)
        res = self.serialize(self.app)
        eq_(res['file_size'], 12345)

    def test_upsell(self):
        self.request.REGION = mkt.regions.USA
        upsell = mkt.site.tests.app_factory()
        self.make_premium(upsell)
        self.app._upsell_from.create(premium=upsell)

        res = self.serialize(self.app)
        eq_(res['upsell']['id'], upsell.id)
        eq_(res['upsell']['app_slug'], upsell.app_slug)
        eq_(res['upsell']['name'], upsell.name)
        eq_(res['upsell']['icon_url'], upsell.get_icon_url(128))
        self.assertApiUrlEqual(res['upsell']['resource_uri'],
                               '/apps/app/%s/' % upsell.id)

    def test_upsell_not_public(self):
        self.request.REGION = mkt.regions.USA
        upsell = mkt.site.tests.app_factory(disabled_by_user=True)
        self.make_premium(upsell)
        self.app._upsell_from.create(premium=upsell)

        res = self.serialize(self.app)
        eq_(res['upsell'], False)

    def test_upsell_excluded_from_region(self):
        self.request.REGION = mkt.regions.USA
        upsell = mkt.site.tests.app_factory()
        self.make_premium(upsell)
        self.app._upsell_from.create(premium=upsell)
        upsell.addonexcludedregion.create(region=mkt.regions.USA.id)

        res = self.serialize(self.app)
        eq_(res['upsell'], False)

    def test_upsell_region_without_payments(self):
        upsell = mkt.site.tests.app_factory()
        self.make_premium(upsell)
        self.app._upsell_from.create(premium=upsell)

        upsell.addonexcludedregion.create(region=mkt.regions.BRA.id)
        self.request.REGION = mkt.regions.BRA

        res = self.serialize(self.app)
        eq_(res['upsell'], False)


class TestAppSerializerPrices(mkt.site.tests.TestCase):
    fixtures = fixture('user_2519')

    def setUp(self):
        self.app = mkt.site.tests.app_factory(premium_type=mkt.ADDON_PREMIUM)
        self.profile = UserProfile.objects.get(pk=2519)
        self.create_flag('override-app-purchase', everyone=True)
        self.request = RequestFactory().get('/')

    def serialize(self, app, profile=None, region=None, request=None):
        if request is None:
            request = self.request
        request.user = self.profile
        request.REGION = region
        a = AppSerializer(instance=app, context={'request': request})
        return a.data

    def test_some_price(self):
        self.make_premium(self.app, price='0.99')
        res = self.serialize(self.app, region=regions.USA)
        eq_(res['price'], Decimal('0.99'))
        eq_(res['price_locale'], '$0.99')
        eq_(res['payment_required'], True)

    def test_no_charge(self):
        self.make_premium(self.app, price='0.00')
        res = self.serialize(self.app, region=regions.USA)
        eq_(res['price'], Decimal('0.00'))
        eq_(res['price_locale'], '$0.00')
        eq_(res['payment_required'], False)

    def test_fallback(self):
        self.make_premium(self.app, price='0.99')
        res = self.serialize(self.app, region=regions.POL)
        eq_(res['price'], Decimal('0.99'))
        eq_(res['price_locale'], '$0.99')
        eq_(res['payment_required'], True)

    def test_fallback_excluded(self):
        self.make_premium(self.app, price='0.99')
        self.app.addonexcludedregion.create(region=RESTOFWORLD.id)
        res = self.serialize(self.app, region=regions.POL)
        eq_(res['price'], None)
        eq_(res['price_locale'], None)
        eq_(res['payment_required'], True)

    def test_with_locale(self):
        premium = self.make_premium(self.app, price='0.99')
        PriceCurrency.objects.create(region=regions.POL.id, currency='PLN',
                                     price='5.01', tier=premium.price,
                                     provider=PROVIDER_REFERENCE)

        with self.activate(locale='fr'):
            res = self.serialize(self.app, region=regions.POL)
            eq_(res['price'], Decimal('5.01'))
            eq_(res['price_locale'], u'5,01\xa0PLN')

    def test_missing_price(self):
        premium = self.make_premium(self.app, price='0.99')
        premium.price = None
        premium.save()

        res = self.serialize(self.app)
        eq_(res['price'], None)
        eq_(res['price_locale'], None)


@mock.patch('mkt.versions.models.Version.is_privileged', False)
class TestESAppSerializer(mkt.site.tests.ESTestCase):
    fixtures = fixture('user_2519', 'webapp_337141')

    def setUp(self):
        self.profile = UserProfile.objects.get(pk=2519)
        self.request = RequestFactory().get('/')
        self.request.REGION = mkt.regions.USA
        self.request.user = self.profile
        self.app = Webapp.objects.get(pk=337141)
        self.version = self.app.current_version
        self.app.update(categories=['books', 'social'])
        Preview.objects.all().delete()
        self.preview = Preview.objects.create(filetype='image/png',
                                              addon=self.app, position=0)
        self.app.description = {
            'en-US': u'XSS attempt <script>alert(1)</script>',
            'fr': u'Déscriptîon in frènch'
        }
        self.app.save()
        self.refresh('webapp')

    def get_obj(self):
        return WebappIndexer.search().filter(
            'term', id=self.app.pk).execute().hits[0]

    def serialize(self):
        serializer = ESAppSerializer(self.get_obj(),
                                     context={'request': self.request})
        return serializer.data

    def test_basic(self):
        res = self.serialize()
        expected = {
            'absolute_url': 'http://testserver/app/something-something/',
            'app_type': 'hosted',
            'author': 'Mozilla Tester',
            'banner_regions': [],
            'categories': ['books', 'social'],
            'created': self.app.created,
            'current_version': '1.0',
            'default_locale': u'en-US',
            'description': {
                'en-US': u'XSS attempt &lt;script&gt;alert(1)&lt;/script&gt;',
                'fr': u'Déscriptîon in frènch'
            },
            'device_types': [],
            'file_size': self.app.file_size,
            'homepage': None,
            'hosted_url': 'http://ngokevin.com',
            'icons': dict((size, self.app.get_icon_url(size))
                          for size in (32, 48, 64, 128)),
            'id': 337141,
            'is_disabled': False,
            'is_offline': False,
            'is_packaged': False,
            'last_updated': self.app.last_updated,
            'manifest_url': 'http://micropipes.com/temp/steamcube.webapp',
            'name': {u'en-US': u'Something Something Steamcube!',
                     u'es': u'Algo Algo Steamcube!'},
            'payment_required': False,
            'premium_type': 'free',
            'previews': [{'filetype': 'image/png',
                          'id': self.preview.id,
                          'image_url': self.preview.image_url,
                          'thumbnail_url': self.preview.thumbnail_url}],
            'privacy_policy': reverse('app-privacy-policy-detail',
                                      kwargs={'pk': self.app.id}),
            'promo_imgs': dict((size, self.app.get_promo_img_url(size))
                               for size in (640, 1920)),
            'public_stats': False,
            'ratings': {
                'average': 0.0,
                'count': 0,
            },
            'reviewed': self.version.reviewed,
            'slug': 'something-something',
            'status': 4,
            'support_url': None,
            'supported_locales': set([u'en-US', u'es', u'pt-BR']),
            'upsell': False,
            # 'version's handled below to support API URL assertions.
        }

        if self.request.user.is_authenticated():
            expected['user'] = {
                'developed': False,
                'installed': False,
                'purchased': False,
            }

        ok_('1.0' in res['versions'])
        self.assertApiUrlEqual(res['versions']['1.0'],
                               '/apps/versions/1268829/')

        for k, v in expected.items():
            assertion = self.assertSetEqual if isinstance(v, set) else eq_
            assertion(
                res[k], v,
                u'Expected value "%s" for field "%s", got "%s"' %
                (v, k, res[k]))

    def test_regions(self):
        res = self.serialize()
        self.assertSetEqual([region['slug'] for region in res['regions']],
                            [region.slug for region in self.app.get_regions()])

    def test_basic_no_queries(self):
        # If we don't pass a UserProfile, a free app shouldn't have to make any
        # db queries at all.
        self.request.user = AnonymousUser()
        with self.assertNumQueries(0):
            self.test_basic()

    def test_basic_with_lang(self):
        # Check that when ?lang is passed, we get the right language and we get
        # empty strings instead of None if the strings don't exist.
        self.request = RequestFactory().get('/?lang=es')
        self.request.REGION = mkt.regions.USA
        self.request.user = AnonymousUser()
        res = self.serialize()
        expected = {
            'id': 337141,
            'description':
                u'XSS attempt &lt;script&gt;alert(1)&lt;/script&gt;',
            'homepage': None,
            'name': u'Algo Algo Steamcube!',
            'support_email': u'foo@bar.com',
            'support_url': None,
        }

        for k, v in expected.items():
            eq_(res[k], v,
                u'Expected value "%s" for field "%s", got "%s"' %
                (v, k, res[k]))

    def test_content_ratings(self):
        self.app.set_content_ratings({
            ratingsbodies.CLASSIND: ratingsbodies.CLASSIND_18,
            ratingsbodies.GENERIC: ratingsbodies.GENERIC_18,
        })
        self.app.set_descriptors(['has_generic_violence', 'has_generic_scary',
                                  'has_classind_shocking'])
        self.app.set_interactives(['has_digital_purchases', 'has_shares_info'])
        self.app.save()
        self.refresh('webapp')

        self.request.REGION = mkt.regions.BGD
        res = self.serialize()
        eq_(res['content_ratings']['body'], 'generic')
        eq_(res['content_ratings']['rating'], '18')
        self.assertSetEqual(
            res['content_ratings']['descriptors'],
            ['has_generic_violence', 'has_generic_scary'])
        self.assertSetEqual(
            res['content_ratings']['descriptors_text'],
            ['Violence', 'Fear'])
        self.assertSetEqual(
            res['content_ratings']['interactives_text'],
            ['Digital Purchases', 'Shares Info'])

        self.request.REGION = mkt.regions.BRA
        res = self.serialize()
        eq_(res['content_ratings']['body'], 'classind')
        eq_(res['content_ratings']['rating'], '18')
        self.assertSetEqual(
            res['content_ratings']['descriptors'],
            ['has_classind_shocking'])

    def test_devices(self):
        AddonDeviceType.objects.create(addon=self.app,
                                       device_type=mkt.DEVICE_GAIA.id)
        self.app.save()
        self.refresh('webapp')

        res = self.serialize()
        eq_(res['device_types'], ['firefoxos'])

    def test_user(self):
        self.app.addonuser_set.create(user=self.profile)
        self.profile.installed_set.create(addon=self.app)
        self.app.addonpurchase_set.create(user=self.profile)
        self.app.save()
        self.refresh('webapp')

        res = self.serialize()
        eq_(res['user'],
            {'developed': True, 'installed': True, 'purchased': True})

    def test_user_not_mine(self):
        Installed.objects.create(addon=self.app, user_id=31337)
        self.app.addonpurchase_set.create(user_id=31337)
        self.app.save()
        self.refresh('webapp')

        res = self.serialize()
        eq_(res['user'],
            {'developed': False, 'installed': False, 'purchased': False})

    def test_no_price(self):
        res = self.serialize()
        eq_(res['price'], None)
        eq_(res['price_locale'], None)

    def test_has_price(self):
        self.make_premium(self.app)
        self.app.save()
        self.refresh('webapp')

        res = self.serialize()
        eq_(res['price'], Decimal('1.00'))
        eq_(res['price_locale'], '$1.00')
        eq_(res['payment_required'], True)

    def test_not_paid(self):
        self.make_premium(self.app)
        PriceCurrency.objects.update(paid=False)
        self.app.save()
        self.refresh('webapp')

        res = self.serialize()
        eq_(res['price'], None)
        eq_(res['price_locale'], None)

    def test_no_currency(self):
        self.make_premium(self.app)
        PriceCurrency.objects.all().delete()
        self.app.save()
        self.refresh('webapp')

        res = self.serialize()
        eq_(res['price'], None)
        eq_(res['price_locale'], None)

    def test_no_payment_account(self):
        eq_(self.serialize()['payment_account'], None)

    def test_payment_account(self):
        self.make_premium(self.app)
        seller = SolitudeSeller.objects.create(
            resource_uri='/path/to/sel', uuid='seller-id', user=self.profile)
        account = PaymentAccount.objects.create(
            user=self.profile, uri='asdf', name='test', inactive=False,
            solitude_seller=seller, account_id=123)
        AddonPaymentAccount.objects.create(
            addon=self.app, account_uri='foo', payment_account=account,
            product_uri='bpruri')
        self.app.save()
        self.refresh('webapp')

        eq_(self.serialize()['payment_account'],
            reverse('payment-account-detail', kwargs={'pk': account.pk}))

    def test_release_notes(self):
        res = self.serialize()
        eq_(res['release_notes'], None)
        version = self.app.current_version
        version.releasenotes = u'These are nötes.'
        version.save()
        self.app.save()
        self.refresh('webapp')
        res = self.serialize()
        eq_(res['release_notes'], {u'en-US': unicode(version.releasenotes)})

        self.request = RequestFactory().get('/?lang=whatever')
        self.request.REGION = mkt.regions.USA
        self.request.user = AnonymousUser()
        res = self.serialize()
        eq_(res['release_notes'], unicode(version.releasenotes))

    def test_upsell(self):
        upsell = mkt.site.tests.app_factory()
        self.make_premium(upsell)
        self.app._upsell_from.create(premium=upsell)
        self.refresh('webapp')

        res = self.serialize()
        eq_(res['upsell']['id'], upsell.id)
        eq_(res['upsell']['app_slug'], upsell.app_slug)
        eq_(res['upsell']['name'], upsell.name)
        eq_(res['upsell']['icon_url'], upsell.get_icon_url(128))
        self.assertApiUrlEqual(res['upsell']['resource_uri'],
                               '/apps/app/%s/' % upsell.id)

    def test_upsell_not_public(self):
        upsell = mkt.site.tests.app_factory(disabled_by_user=True)
        self.make_premium(upsell)
        self.app._upsell_from.create(premium=upsell)
        self.refresh('webapp')

        res = self.serialize()
        eq_(res['upsell'], False)

    def test_upsell_is_made_public_later(self):
        upsell = mkt.site.tests.app_factory(status=mkt.STATUS_PENDING)
        self.make_premium(upsell)
        self.app._upsell_from.create(premium=upsell)

        # Don't use .reload() because it doesn't reset cached_property.
        upsell = Webapp.objects.get(pk=upsell.pk)
        upsell.update(status=mkt.STATUS_PUBLIC)

        # Note that we shouldn't have to call self.app.save(), because saving
        # the upsell should have triggered the reindex of self.app.
        self.refresh('webapp')

        res = self.serialize()
        eq_(res['upsell']['id'], upsell.id)
        eq_(res['upsell']['app_slug'], upsell.app_slug)
        eq_(res['upsell']['name'], upsell.name)
        eq_(res['upsell']['icon_url'], upsell.get_icon_url(128))
        self.assertApiUrlEqual(res['upsell']['resource_uri'],
                               '/apps/app/%s/' % upsell.id)

    def test_upsell_excluded_from_region(self):
        upsell = mkt.site.tests.app_factory()
        upsell.addonexcludedregion.create(region=mkt.regions.USA.id)
        self.make_premium(upsell)
        self.app._upsell_from.create(premium=upsell)
        self.refresh('webapp')

        res = self.serialize()
        eq_(res['upsell'], False)

    def test_upsell_region_without_payments(self):
        upsell = mkt.site.tests.app_factory()
        upsell.addonexcludedregion.create(region=mkt.regions.BRA.id)
        self.make_premium(upsell)
        self.app._upsell_from.create(premium=upsell)
        self.refresh('webapp')

        self.request.REGION = mkt.regions.BRA
        res = self.serialize()
        eq_(res['upsell'], False)

    def test_developer_name_empty(self):
        self.app.current_version.update(_developer_name='')
        self.app.addonuser_set.update(listed=False)
        self.app.save()
        self.refresh('webapp')
        res = self.serialize()
        eq_(res['author'], '')

    def test_feed_collection_group(self):
        app = WebappIndexer.search().filter(
            'term', id=self.app.pk).execute().hits[0]
        app['group_translations'] = [{'lang': 'en-US', 'string': 'My Group'}]
        res = ESAppSerializer(app, context={'request': self.request})
        eq_(res.data['group'], {'en-US': 'My Group'})


class TestSimpleESAppSerializer(mkt.site.tests.ESTestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        self.webapp = Webapp.objects.get(pk=337141)
        self.request = RequestFactory().get('/')
        self.request.user = AnonymousUser()
        RegionMiddleware().process_request(self.request)
        self.reindex(Webapp)
        self.indexer = WebappIndexer.search().filter(
            'term', id=self.webapp.id).execute().hits[0]
        self.serializer = SimpleESAppSerializer(
            self.indexer,
            context={'request': self.request})

    def test_regions_present(self):
        # Regression test for bug 964802.
        ok_('regions' in self.serializer.data)
        eq_(len(self.serializer.data['regions']),
            len(self.webapp.get_regions()))

    def test_categories_present(self):
        ok_('categories' in self.serializer.data)
