import urlparse
from urllib import urlencode

from django.conf import settings
from django.test.utils import override_settings

import jwt
from mozpay.verify import verify_claims, verify_keys
from nose.tools import eq_, raises

from amo.helpers import absolutify
from constants.payments import PROVIDER_BOKU
from mkt.developers.models import AddonPaymentAccount, PaymentAccount
from amo.urlresolvers import reverse
from mkt.purchase.models import Contribution
from mkt.purchase.tests.utils import InAppPurchaseTest, PurchaseTest
from mkt.webpay.webpay_jwt import (get_product_jwt, InAppProduct,
                                   WebAppProduct)


class TestPurchaseJWT(PurchaseTest):

    def setUp(self):
        super(TestPurchaseJWT, self).setUp()
        self.product = WebAppProduct(self.addon)
        self.contribution = Contribution.objects.create(
            user=self.user,
            addon=self.addon,
        )

    def decode_token(self):
        token = get_product_jwt(self.product, self.contribution)
        return jwt.decode(str(token['webpayJWT']), verify=False)

    def test_claims(self):
        verify_claims(self.decode_token())

    def test_keys(self):
        verify_keys(self.decode_token(),
                    ('iss',
                     'typ',
                     'aud',
                     'iat',
                     'exp',
                     'request.name',
                     'request.description',
                     'request.pricePoint',
                     'request.postbackURL',
                     'request.chargebackURL',
                     'request.productData'))

    def test_valid_jwt(self):
        token_data = self.decode_token()
        eq_(token_data['iss'], settings.APP_PURCHASE_KEY)
        eq_(token_data['typ'], settings.APP_PURCHASE_TYP)
        eq_(token_data['aud'], settings.APP_PURCHASE_AUD)

        request = token_data['request']
        eq_(request['id'], self.product.external_id())
        eq_(request['name'], self.product.name())
        eq_(request['icons'], self.product.icons())
        eq_(request['description'], self.product.description())
        eq_(request['pricePoint'], self.product.price().name)
        eq_(request['postbackURL'], absolutify(reverse('webpay.postback')))
        eq_(request['chargebackURL'], absolutify(reverse('webpay.chargeback')))

        token_product_data = urlparse.parse_qs(request['productData'])
        expected_product_data = urlparse.parse_qs(
            urlencode(self.product.product_data(self.contribution)))
        eq_(token_product_data, expected_product_data)

    @raises(ValueError)
    def test_empty_public_id(self):
        self.addon.update(solitude_public_id=None)
        self.decode_token()


class BaseTestWebAppProduct(PurchaseTest):
    def setUp(self):
        super(BaseTestWebAppProduct, self).setUp()
        self.product = WebAppProduct(self.addon)
        self.contribution = Contribution.objects.create(
            user=self.user,
            addon=self.addon,
        )
        self.contribution = Contribution.objects.get()


class TestWebAppProduct(BaseTestWebAppProduct):
    def test_external_id_with_no_domain(self):
        with self.settings(DOMAIN=None):
            eq_(self.product.external_id(),
                'marketplace-dev:{0}'.format(self.addon.pk))

    def test_external_id_with_domain(self):
        with self.settings(DOMAIN='marketplace.allizom.org'):
            eq_(self.product.external_id(),
                'marketplace:{0}'.format(self.addon.pk))

    def test_webapp_product(self):
        eq_(self.product.id(), self.addon.pk)
        eq_(self.product.name(), unicode(self.addon.name))
        eq_(self.product.addon(), self.addon)
        eq_(self.product.price(), self.addon.premium.price)
        eq_(self.product.icons()['64'],
            absolutify(self.addon.get_icon_url(64)))
        eq_(self.product.description(), self.addon.description)
        eq_(self.product.application_size(),
            self.addon.current_version.all_files[0].size)

        product_data = self.product.product_data(self.contribution)
        eq_(product_data['contrib_uuid'], self.contribution.uuid)
        eq_(product_data['public_id'], self.public_id)
        eq_(product_data['addon_id'], self.product.addon().pk)
        eq_(product_data['application_size'], self.product.application_size())


@override_settings(PAYMENT_PROVIDERS=['bango', 'boku'])
class TestWebAppProductMultipleProviders(BaseTestWebAppProduct):
    def setUp(self):
        super(TestWebAppProductMultipleProviders, self).setUp()
        account = PaymentAccount.objects.create(
            user=self.user, uri='foo', name='test', inactive=False,
            solitude_seller=self.seller, account_id=321, seller_uri='abc',
            provider=PROVIDER_BOKU)
        AddonPaymentAccount.objects.create(
            addon=self.addon, account_uri='foo',
            payment_account=account, product_uri='newuri')

    def test_webapp_product_multiple_providers(self):
        product_data = self.product.product_data(self.contribution)
        eq_(product_data['contrib_uuid'], self.contribution.uuid)
        eq_(product_data['public_id'], self.public_id)
        eq_(product_data['addon_id'], self.product.addon().pk)
        eq_(product_data['application_size'],
            self.product.application_size())


class TestInAppProduct(InAppPurchaseTest):

    def setUp(self):
        super(TestInAppProduct, self).setUp()
        self.contribution = Contribution.objects.create(
            user=self.user,
            addon=self.addon,
        )
        self.product = InAppProduct(self.inapp)

    def test_external_id_with_no_domain(self):
        with self.settings(DOMAIN=None):
            eq_(self.product.external_id(),
                'inapp.marketplace-dev:{0}'.format(self.inapp.pk))

    def test_external_id_with_domain(self):
        with self.settings(DOMAIN='marketplace.allizom.org'):
            eq_(self.product.external_id(),
                'inapp.marketplace:{0}'.format(self.inapp.pk))

    def test_inapp_product(self):
        eq_(self.product.id(), self.inapp.pk)
        eq_(self.product.name(), unicode(self.inapp.name))
        eq_(self.product.addon(), self.inapp.webapp)
        eq_(self.product.price(), self.inapp.price)
        eq_(self.product.icons()[64], absolutify(self.inapp.logo_url))
        eq_(self.product.description(), self.inapp.webapp.description)
        eq_(self.product.application_size(), None)

        product_data = self.product.product_data(self.contribution)
        eq_(product_data['contrib_uuid'], self.contribution.uuid)
        eq_(product_data['addon_id'], self.product.addon().pk)
        eq_(product_data['inapp_id'], self.product.id())
        eq_(product_data['application_size'], self.product.application_size())
        eq_(product_data['public_id'], self.public_id)

    def test_no_url(self):
        self.inapp.logo_url = None
        eq_(self.product.icons()[64],
            'http://testserver/img/mkt/icons/rocket-64.png')
