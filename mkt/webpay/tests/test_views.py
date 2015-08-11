import json
import uuid
from decimal import Decimal
from urlparse import parse_qs

from django.conf import settings
from django.core import mail
from django.core.urlresolvers import reverse
from django.http import HttpRequest

import jwt
from mock import patch
from nose.tools import eq_, ok_

import mkt
from mkt import CONTRIB_PENDING, CONTRIB_PURCHASE
from lib.crypto.receipt import crack
from mkt.access.models import GroupUser
from mkt.api.tests import BaseAPI
from mkt.api.tests.test_oauth import RestOAuth
from mkt.constants import regions
from mkt.constants.payments import PROVIDER_BANGO
from mkt.inapp.models import InAppProduct
from mkt.prices.models import Price, PriceCurrency
from mkt.prices.views import PricesViewSet
from mkt.purchase.models import Contribution
from mkt.purchase.tests.utils import InAppPurchaseTest, PurchaseTest
from mkt.site.fixtures import fixture
from mkt.site.tests import TestCase
from mkt.users.models import UserProfile
from mkt.webapps.models import Webapp
from mkt.webpay.models import ProductIcon


@patch('mkt.regions.middleware.RegionMiddleware.region_from_request',
       lambda s, r: mkt.regions.USA)
class TestPrepareWebApp(PurchaseTest, RestOAuth):
    fixtures = fixture('webapp_337141', 'user_2519', 'prices')

    def setUp(self):
        RestOAuth.setUp(self)  # Avoid calling PurchaseTest.setUp().
        self.user = UserProfile.objects.get(pk=2519)
        self.list_url = reverse('webpay-prepare')
        self.setup_base()
        self.setup_package()
        self.setup_mock_generic_product()
        self.setup_public_id()

    def _post(self, client=None, extra_headers=None):
        if client is None:
            client = self.client
        if extra_headers is None:
            extra_headers = {}
        return client.post(self.list_url,
                           data=json.dumps({'app': self.webapp.pk}),
                           **extra_headers)

    def test_allowed(self):
        self._allowed_verbs(self.list_url, ['post'])

    def test_anon(self):
        res = self._post(self.anon)
        eq_(res.status_code, 403)
        eq_(res.json,
            {'detail': 'Authentication credentials were not provided.'})

    def test_unsupported_region(self):
        with patch('mkt.webapps.models.Webapp.get_price_region_ids') as r:
            # Make this app support the wrong region and disable worldwide.
            r.return_value = [mkt.regions.CHN.id]
            res = self._post()
        eq_(res.status_code, 403)
        eq_(res.json, {'reason': 'Payments are restricted for this region'})

    def test_unsupported_region_but_worldwide_allowed(self):
        with patch('mkt.webapps.models.Webapp.get_price_region_ids') as r:
            # Make this app support the wrong region but enable worldwide.
            r.return_value = [mkt.regions.CHN.id, mkt.regions.RESTOFWORLD.id]
            res = self._post()
        eq_(res.status_code, 201)

    def test_get_jwt(self, client=None, extra_headers=None):
        res = self._post(client=client, extra_headers=extra_headers)
        eq_(res.status_code, 201, res.content)
        contribution = Contribution.objects.get()
        eq_(res.json['contribStatusURL'],
            reverse('webpay-status', kwargs={'uuid': contribution.uuid}))
        ok_(res.json['webpayJWT'])
        eq_(res['Access-Control-Allow-Headers'],
            'content-type, accept, x-fxpay-version')

    @patch.object(settings, 'SECRET_KEY', 'gubbish')
    def test_good_shared_secret(self):
        # Like test_good, except we do shared secret auth manually.
        extra_headers = {
            'HTTP_AUTHORIZATION': 'mkt-shared-secret '
                                  'cfinke@m.com,56b6f1a3dd735d962c56'
                                  'ce7d8f46e02ec1d4748d2c00c407d75f0969d08bb'
                                  '9c68c31b3371aa8130317815c89e5072e31bb94b4'
                                  '121c5c165f3515838d4d6c60c4,165d631d3c3045'
                                  '458b4516242dad7ae'
        }
        self.user.update(email='cfinke@m.com')
        self.test_get_jwt(client=self.anon, extra_headers=extra_headers)

    @patch('mkt.webapps.models.Webapp.has_purchased')
    def test_already_purchased(self, has_purchased):
        has_purchased.return_value = True
        res = self._post()
        eq_(res.status_code, 409)
        eq_(res.json, {"reason": "Already purchased app."})


class TestPrepareInApp(InAppPurchaseTest, RestOAuth):
    fixtures = fixture('webapp_337141', 'user_2519', 'prices')

    def setUp(self):
        RestOAuth.setUp(self)  # Avoid calling PurchaseTest.setUp().
        self.user = UserProfile.objects.get(pk=2519)
        self.setup_base()
        self.setup_package()
        self.setup_public_id()
        self.list_url = reverse('webpay-prepare-inapp')

    def _post(self, inapp_guid=None, extra_headers=None):
        inapp_guid = inapp_guid or self.inapp.guid
        extra_headers = extra_headers or {}
        return self.anon.post(self.list_url,
                              data=json.dumps({'inapp': inapp_guid}),
                              **extra_headers)

    def test_allowed(self):
        self._allowed_verbs(self.list_url, ['post'])

    def test_bad_id_raises_400(self):
        res = self._post(inapp_guid='invalid id')
        eq_(res.status_code, 400, res.content)

    def test_non_public_parent_app_fails(self):
        self.webapp.update(status=mkt.STATUS_PENDING)
        res = self._post()
        eq_(res.status_code, 400, res.content)

    def test_inactive_app_fails(self):
        self.inapp.update(active=False)
        res = self._post()
        eq_(res.status_code, 400, res.content)

    def test_simulated_app_with_non_public_parent_succeeds(self):
        self.webapp.update(status=mkt.STATUS_PENDING)
        self.inapp.update(simulate=json.dumps({'result': 'postback'}))
        res = self._post()
        eq_(res.status_code, 201, res.content)

    def test_simulated_app_without_parent_succeeds(self):
        self.inapp.update(simulate=json.dumps({'result': 'postback'}),
                          webapp=None)
        res = self._post()
        eq_(res.status_code, 201, res.content)

    def test_get_jwt(self, extra_headers=None):
        res = self._post(extra_headers=extra_headers)
        eq_(res.status_code, 201, res.content)
        contribution = Contribution.objects.get()
        eq_(contribution.webapp, self.inapp.webapp)
        eq_(contribution.inapp_product, self.inapp)
        eq_(res.json['contribStatusURL'],
            reverse('webpay-status', kwargs={'uuid': contribution.uuid}))
        ok_(res.json['webpayJWT'])
        eq_(res['Access-Control-Allow-Headers'],
            'content-type, accept, x-fxpay-version')

    def test_get_simulated_jwt(self):
        self.inapp.webapp = None
        self.inapp.simulate = json.dumps({'result': 'postback'})
        self.inapp.stub = True
        self.inapp.save()

        res = self._post()
        eq_(res.status_code, 201, res.content)

        contribution = Contribution.objects.get()
        eq_(contribution.webapp, None)
        eq_(contribution.inapp_product, self.inapp)
        eq_(res.json['contribStatusURL'],
            reverse('webpay-status', kwargs={'uuid': contribution.uuid}))

        token = jwt.decode(res.json['webpayJWT'].encode('utf8'), verify=False)
        eq_(token['request']['simulate'], {'result': 'postback'})


class TestStatus(BaseAPI):
    fixtures = fixture('prices', 'webapp_337141', 'user_2519')

    def setUp(self):
        super(TestStatus, self).setUp()
        self.webapp = Webapp.objects.get(pk=337141)
        self.price = Price.objects.get(pk=1)
        self.user = UserProfile.objects.get(pk=2519)

    def get_inapp_product(self, **kw):
        params = dict(logo_url='logo.png',
                      name='Magical Unicorn',
                      price=self.price,
                      webapp=self.webapp)
        params.update(kw)
        return InAppProduct.objects.create(**params)

    def get_contribution(self, user=None, inapp=None, **kw):
        if 'webapp' not in kw:
            kw['webapp'] = self.webapp
        webapp = kw.pop('webapp')
        return Contribution.objects.create(
            webapp=webapp,
            inapp_product=inapp,
            type=CONTRIB_PURCHASE,
            user=user or self.user,
            uuid=str(uuid.uuid4()),
        )

    def get_contribution_url(self, contribution=None):
        contribution = contribution or self.get_contribution()
        return reverse('webpay-status', kwargs={'uuid': contribution.uuid})

    def get_status(self, url=None, expected_status=200):
        url = url or self.get_contribution_url()
        res = self.client.get(url)
        eq_(res.status_code, expected_status, res)
        return json.loads(res.content)

    def validate_inapp_receipt(self, receipt, contribution):
        eq_(receipt['typ'], 'purchase-receipt')
        eq_(receipt['product']['url'], contribution.webapp.origin)
        storedata = parse_qs(receipt['product']['storedata'])
        eq_(storedata['id'][0], str(contribution.webapp.pk))
        eq_(storedata['contrib'][0], str(contribution.pk))
        eq_(storedata['inapp_id'][0], str(contribution.inapp_product.guid))
        assert 'user' in receipt, (
            'The web platform requires a user value')

    def test_allowed(self):
        self._allowed_verbs(self.get_contribution_url(), ['get'])

    def test_get(self):
        data = self.get_status(self.get_contribution_url())
        eq_(data['status'], 'complete')
        # Normal transactions should not produce receipts.
        eq_(data['receipt'], None)

    def test_fxpay_version_header(self):
        res = self.client.get(self.get_contribution_url())
        eq_(res['Access-Control-Allow-Headers'],
            'content-type, accept, x-fxpay-version')

    def test_completed_inapp_purchase(self):
        contribution = self.get_contribution(inapp=self.get_inapp_product())
        data = self.get_status(self.get_contribution_url(contribution))
        eq_(data['status'], 'complete')
        receipt = crack(data['receipt'])[0]
        self.validate_inapp_receipt(receipt, contribution)

    def test_completed_inapp_simulation(self):
        inapp = self.get_inapp_product(
            webapp=None, simulate=json.dumps({'result': 'postback'}))
        contribution = self.get_contribution(inapp=inapp, webapp=None)

        data = self.get_status(self.get_contribution_url(contribution))
        eq_(data['status'], 'complete')

        receipt = crack(data['receipt'])[0]
        eq_(receipt['typ'], 'test-receipt')
        eq_(receipt['product']['url'], settings.SITE_URL)

        storedata = parse_qs(receipt['product']['storedata'])
        eq_(storedata['id'][0], '0')
        eq_(storedata['contrib'][0], str(contribution.pk))
        eq_(storedata['inapp_id'][0], str(contribution.inapp_product.guid))

    def test_no_contribution(self):
        contribution = self.get_contribution()
        url = self.get_contribution_url(contribution)
        contribution.delete()
        data = self.get_status(url=url)
        eq_(data['status'], 'incomplete')

    def test_incomplete(self):
        contribution = self.get_contribution()
        contribution.update(type=CONTRIB_PENDING)
        data = self.get_status(url=self.get_contribution_url(contribution))
        eq_(data['status'], 'incomplete')

    def test_not_owner(self):
        user2 = UserProfile.objects.get(pk=31337)
        contribution = self.get_contribution(user=user2)
        # Not owning a contribution is okay.
        data = self.get_status(self.get_contribution_url(contribution))
        eq_(data['status'], 'complete')


@patch('mkt.regions.middleware.RegionMiddleware.region_from_request',
       lambda s, r: mkt.regions.BRA)
class TestPrices(RestOAuth):

    def make_currency(self, amount, tier, currency, region):
        return PriceCurrency.objects.create(
            price=Decimal(amount), tier=tier,
            currency=currency, provider=PROVIDER_BANGO, region=region.id)

    def setUp(self):
        super(TestPrices, self).setUp()
        self.price = Price.objects.create(name='1', price=Decimal(1))
        self.currency = self.make_currency(3, self.price, 'DE', regions.DEU)
        self.us_currency = self.make_currency(3, self.price, 'USD',
                                              regions.USA)
        self.list_url = reverse('price-list')
        self.get_url = reverse('price-detail', kwargs={'pk': self.price.pk})

    def get_currencies(self, data):
        return [p['currency'] for p in data['prices']]

    def test_list_allowed(self):
        self._allowed_verbs(self.list_url, ['get'])
        self._allowed_verbs(self.get_url, ['get'])

    def test_single(self):
        res = self.client.get(self.get_url)
        eq_(res.status_code, 200)
        eq_(res.json['pricePoint'], '1')
        eq_(res.json['name'], 'Tier 1')
        # Ensure that price is in the JSON since solitude depends upon it.
        eq_(res.json['price'], '1.00')

    def test_list_filtered_price_point(self):
        Price.objects.create(name='42', price=Decimal(42))
        res = self.client.get(self.list_url, {'pricePoint': '1'})
        eq_(res.status_code, 200)
        data = json.loads(res.content)
        eq_(data['meta']['total_count'], 1)
        eq_(data['objects'][0]['pricePoint'], '1')

    def test_list(self):
        res = self.client.get(self.list_url)
        eq_(res.json['meta']['total_count'], 1)
        self.assertSetEqual(self.get_currencies(res.json['objects'][0]),
                            ['USD', 'DE'])

    def test_list_filtered_provider(self):
        self.currency.update(provider=0)
        res = self.client.get(self.list_url, {'provider': 'bango'})
        eq_(self.get_currencies(res.json['objects'][0]), ['USD'])

    def test_prices(self):
        res = self.client.get(self.get_url)
        eq_(res.status_code, 200)
        self.assertSetEqual(self.get_currencies(res.json), ['USD', 'DE'])

    def test_prices_filtered_provider(self):
        self.currency.update(provider=0)
        res = self.client.get(self.get_url, {'provider': 'bango'})
        eq_(res.status_code, 200)
        self.assertSetEqual(self.get_currencies(res.json), ['USD'])

    def test_has_cors(self):
        self.assertCORS(self.client.get(self.get_url), 'get')

    @patch('mkt.api.exceptions.got_request_exception')
    @patch('mkt.prices.models.Price.prices')
    def test_other_cors(self, prices, got_request_exception):
        prices.side_effect = ValueError('The Price Is Not Right.')
        res = self.client.get(self.get_url)
        eq_(res.status_code, 500)
        self.assertCORS(res, 'get')
        exception_handler_args = got_request_exception.send.call_args
        eq_(exception_handler_args[0][0], PricesViewSet)
        eq_(exception_handler_args[1]['request'].path, self.get_url)
        ok_(isinstance(exception_handler_args[1]['request'], HttpRequest))

    def test_locale(self):
        self.make_currency(5, self.price, 'BRL', regions.BRA)
        res = self.client.get(self.get_url, HTTP_ACCEPT_LANGUAGE='pt-BR')
        eq_(res.status_code, 200)
        eq_(res.json['localized']['locale'], 'R$5,00')

    def test_locale_list(self):
        # Check that for each price tier a different localisation is
        # returned.
        self.make_currency(2, self.price, 'BRL', regions.BRA)
        price_two = Price.objects.create(name='2', price=Decimal(1))
        self.make_currency(12, price_two, 'BRL', regions.BRA)

        res = self.client.get(self.list_url, HTTP_ACCEPT_LANGUAGE='pt-BR')
        eq_(res.status_code, 200)
        eq_(res.json['objects'][0]['localized']['locale'], 'R$2,00')
        eq_(res.json['objects'][1]['localized']['locale'], 'R$12,00')

    def test_no_locale(self):
        # This results in a region of BR and a currency of BRL. But there
        # isn't a price tier for that currency. So we don't know what to show.
        res = self.client.get(self.get_url, HTTP_ACCEPT_LANGUAGE='pt-BR')
        eq_(res.status_code, 200)
        eq_(res.json['localized'], {})


class TestNotification(RestOAuth):
    fixtures = fixture('webapp_337141', 'user_2519')

    def setUp(self):
        super(TestNotification, self).setUp()
        self.grant_permission(self.profile, 'Transaction:NotifyFailure')
        self.contribution = Contribution.objects.create(webapp_id=337141,
                                                        uuid='sample:uuid')
        self.get_url = reverse('webpay-failurenotification',
                               kwargs={'pk': self.contribution.pk})
        self.data = {'url': 'https://someserver.com', 'attempts': 5}

    def test_list_allowed(self):
        self._allowed_verbs(self.get_url, ['patch'])

    def test_notify(self):
        res = self.client.patch(self.get_url, data=json.dumps(self.data))
        eq_(res.status_code, 202)
        eq_(len(mail.outbox), 1)
        msg = mail.outbox[0]
        assert self.data['url'] in msg.body
        eq_(msg.recipients(), [u'steamcube@mozilla.com'])

    def test_no_permission(self):
        GroupUser.objects.filter(user=self.profile).delete()
        res = self.client.patch(self.get_url, data=json.dumps(self.data))
        eq_(res.status_code, 403)

    def test_missing(self):
        res = self.client.patch(self.get_url, data=json.dumps({}))
        eq_(res.status_code, 400)

    def test_not_there(self):
        self.get_url = reverse('webpay-failurenotification',
                               kwargs={'pk': self.contribution.pk + 42})
        res = self.client.patch(self.get_url, data=json.dumps(self.data))
        eq_(res.status_code, 404)

    def test_no_uuid(self):
        self.contribution.update(uuid=None)
        res = self.client.patch(self.get_url, data=json.dumps(self.data))
        eq_(res.status_code, 404)


class TestProductIconResource(RestOAuth):
    fixtures = fixture('webapp_337141', 'user_2519')

    def setUp(self):
        super(TestProductIconResource, self).setUp()
        self.list_url = reverse('producticon-list')
        p = patch('mkt.webpay.tasks.fetch_product_icon')
        self.fetch_product_icon = p.start()
        self.addCleanup(p.stop)
        self.data = {
            'ext_size': 128,
            'ext_url': 'http://someappnoreally.com/icons/icon_128.png',
            'size': 64
        }

    def post(self, data, with_perms=True):
        if with_perms:
            self.grant_permission(self.profile, 'ProductIcon:Create')
        return self.client.post(self.list_url, data=json.dumps(data))

    def test_list_allowed(self):
        self._allowed_verbs(self.list_url, ['get', 'post'])

    def test_missing_fields(self):
        res = self.post({'ext_size': 1})
        eq_(res.status_code, 400)

    def test_post(self):
        res = self.post(self.data)
        eq_(res.status_code, 202)
        self.fetch_product_icon.delay.assert_called_with(self.data['ext_url'],
                                                         self.data['ext_size'],
                                                         self.data['size'])

    def test_post_without_perms(self):
        res = self.post(self.data, with_perms=False)
        eq_(res.status_code, 403)

    def test_anon_get_filtering(self):
        icon = ProductIcon.objects.create(**{
            'ext_size': 128,
            'ext_url': 'http://someappnoreally.com/icons/icon_128.png',
            'size': 64,
            'format': 'png'
        })
        extra_icon = ProductIcon.objects.create(**{
            'ext_size': 256,
            'ext_url': 'http://someappnoreally.com/icons/icon_256.png',
            'size': 64,
            'format': 'png'
        })
        res = self.anon.get(self.list_url)
        eq_(res.status_code, 200)
        data = json.loads(res.content)
        eq_(len(data['objects']), 2)

        res = self.anon.get(self.list_url, data={'ext_size': 128})
        eq_(res.status_code, 200)
        data = json.loads(res.content)
        eq_(len(data['objects']), 1)
        eq_(data['objects'][0]['url'], icon.url())

        res = self.anon.get(self.list_url, data={'size': 64})
        eq_(res.status_code, 200)
        data = json.loads(res.content)
        eq_(len(data['objects']), 2)

        res = self.anon.get(
            self.list_url,
            data={'ext_url': 'http://someappnoreally.com/icons/icon_256.png'})
        eq_(res.status_code, 200)
        data = json.loads(res.content)
        eq_(len(data['objects']), 1)
        eq_(data['objects'][0]['url'], extra_icon.url())


class TestSigCheck(TestCase):

    def test(self):
        key = 'marketplace'
        aud = 'webpay'
        secret = 'third door on the right'
        with self.settings(APP_PURCHASE_SECRET=secret,
                           APP_PURCHASE_KEY=key,
                           APP_PURCHASE_AUD=aud):
            res = self.client.post(reverse('webpay-sig_check'))
        eq_(res.status_code, 201, res)
        data = json.loads(res.content)
        req = jwt.decode(data['sig_check_jwt'].encode('ascii'), secret)
        eq_(req['iss'], key)
        eq_(req['aud'], aud)
        eq_(req['typ'], 'mozilla/payments/sigcheck/v1')
