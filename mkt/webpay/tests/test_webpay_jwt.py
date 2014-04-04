import urlparse
from urllib import urlencode

from django.conf import settings

import jwt
from mozpay.verify import verify_claims, verify_keys
from nose.tools import eq_

import amo
from amo.helpers import absolutify
from amo.urlresolvers import reverse
from mkt.webpay.webpay_jwt import (get_product_jwt, WebAppProduct,
                                     InAppProduct)
from mkt import regions
from mkt.purchase.tests.utils import InAppPurchaseTest, PurchaseTest
from stats.models import Contribution


class TestPurchaseJWT(PurchaseTest):

    def setUp(self):
        super(TestPurchaseJWT, self).setUp()
        self.product = WebAppProduct(self.addon)
        self.token = get_product_jwt(
            self.product,
            region=regions.US,
            user=self.user,
        )

        self.token_data = jwt.decode(
            str(self.token['webpayJWT']), verify=False)

        self.contribution = Contribution.objects.get()

    def test_claims(self):
        verify_claims(self.token_data)

    def test_keys(self):
        verify_keys(self.token_data,
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
        eq_(self.token_data['iss'], settings.APP_PURCHASE_KEY)
        eq_(self.token_data['typ'], settings.APP_PURCHASE_TYP)
        eq_(self.token_data['aud'], settings.APP_PURCHASE_AUD)

        contribution = Contribution.objects.get()
        eq_(contribution.type, amo.CONTRIB_PENDING)
        eq_(contribution.price_tier, self.addon.premium.price)
        eq_(contribution.user, self.user)

        request = self.token_data['request']
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


class TestWebAppProduct(PurchaseTest):

    def setUp(self):
        super(TestWebAppProduct, self).setUp()
        self.product = WebAppProduct(self.addon)
        self.token = get_product_jwt(
            self.product,
            region=regions.US,
            user=self.user,
        )

        self.contribution = Contribution.objects.get()

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
        eq_(self.product.amount(regions.US),
            self.addon.get_price(region=regions.US.id))
        eq_(self.product.price(), self.addon.premium.price)
        eq_(self.product.icons()['512'],
            absolutify(self.addon.get_icon_url(512)))
        eq_(self.product.description(), self.addon.description)
        eq_(self.product.application_size(),
            self.addon.current_version.all_files[0].size)
        eq_(self.product.seller_uuid(), (self.addon
                                             .single_pay_account()
                                             .payment_account
                                             .solitude_seller
                                             .uuid))

        product_data = self.product.product_data(self.contribution)
        eq_(product_data['contrib_uuid'], self.contribution.uuid)
        eq_(product_data['seller_uuid'], self.product.seller_uuid())
        eq_(product_data['addon_id'], self.product.addon().pk)
        eq_(product_data['application_size'], self.product.application_size())


class TestInAppProduct(InAppPurchaseTest):

    def setUp(self):
        super(TestInAppProduct, self).setUp()
        self.product = InAppProduct(self.inapp)
        self.token = get_product_jwt(self.product)
        self.contribution = Contribution.objects.get()

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
        eq_(self.product.amount(regions.US), None)
        eq_(self.product.price(), self.inapp.price)
        eq_(self.product.icons()[64], absolutify(self.inapp.logo_url))
        eq_(self.product.description(), self.inapp.webapp.description)
        eq_(self.product.application_size(), None)
        eq_(self.product.seller_uuid(), (self.inapp
                                             .webapp
                                             .single_pay_account()
                                             .payment_account
                                             .solitude_seller
                                             .uuid))

        product_data = self.product.product_data(self.contribution)
        eq_(product_data['contrib_uuid'], self.contribution.uuid)
        eq_(product_data['seller_uuid'], self.product.seller_uuid())
        eq_(product_data['addon_id'], self.product.addon().pk)
        eq_(product_data['inapp_id'], self.product.id())
        eq_(product_data['application_size'], self.product.application_size())
