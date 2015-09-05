# -*- coding: utf-8 -*-
import json
import urlparse
from urllib import urlencode

from django.conf import settings
from django.core.urlresolvers import reverse
from django.test.utils import override_settings

import jwt
import mock
from mozpay.verify import verify_claims, verify_keys
from nose.tools import eq_, ok_, raises

from mkt.constants.payments import PROVIDER_REFERENCE
from mkt.developers.models import WebappPaymentAccount, PaymentAccount
from mkt.purchase.models import Contribution
from mkt.purchase.tests.utils import InAppPurchaseTest, PurchaseTest
from mkt.site.helpers import absolutify
from mkt.webpay.webpay_jwt import (get_product_jwt, InAppProduct,
                                   SimulatedInAppProduct, WebAppProduct)


class TestPurchaseJWT(PurchaseTest):

    def setUp(self):
        super(TestPurchaseJWT, self).setUp()
        self.product = WebAppProduct(self.webapp)
        self.contribution = Contribution.objects.create(
            user=self.user,
            webapp=self.webapp,
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
        eq_(request['defaultLocale'], self.product.default_locale())
        eq_(request['icons'], self.product.icons())
        eq_(request['description'], self.product.description())
        eq_(request['pricePoint'], self.product.price().name)
        eq_(request['postbackURL'], absolutify(reverse('webpay.postback')))
        eq_(request['chargebackURL'], absolutify(reverse('webpay.chargeback')))

        product = urlparse.parse_qs(request['productData'])
        expected = urlparse.parse_qs(
            urlencode(self.product.product_data(self.contribution)))
        eq_(product['buyer_email'], [self.user.email])
        eq_(product, expected)

    @raises(ValueError)
    def test_empty_public_id(self):
        self.webapp.update(solitude_public_id=None)
        self.decode_token()

    def test_no_user(self):
        self.contribution.update(user=None)
        token_data = self.decode_token()
        request = token_data['request']
        product = urlparse.parse_qs(request['productData'])
        ok_('buyer_email' not in product)

    def test_locales(self):
        with mock.patch.object(self.product, 'localized_properties') as props:
            loc_data = {
                'es': {
                    'name': 'El Mocoso',
                    'description': u'descripción de la aplicación',
                }
            }
            props.return_value = loc_data
            token_data = self.decode_token()
            # Make sure the JWT passes through localized_properties() data.
            eq_(token_data['request']['locales'], loc_data)


class BaseTestWebAppProduct(PurchaseTest):
    def setUp(self):
        super(BaseTestWebAppProduct, self).setUp()
        self.product = WebAppProduct(self.webapp)
        self.contribution = Contribution.objects.create(
            user=self.user,
            webapp=self.webapp,
        )
        self.contribution = Contribution.objects.get()


class TestWebAppProduct(BaseTestWebAppProduct):

    def test_external_id_with_no_domain(self):
        with self.settings(DOMAIN=None):
            eq_(self.product.external_id(),
                'marketplace-dev:{0}'.format(self.webapp.pk))

    def test_external_id_with_domain(self):
        with self.settings(DOMAIN='marketplace.allizom.org'):
            eq_(self.product.external_id(),
                'marketplace:{0}'.format(self.webapp.pk))

    def test_webapp_product(self):
        eq_(self.product.id(), self.webapp.pk)
        eq_(self.product.name(), unicode(self.webapp.name))
        eq_(self.product.webapp(), self.webapp)
        eq_(self.product.default_locale(), self.webapp.default_locale)
        eq_(self.product.price(), self.webapp.premium.price)
        eq_(self.product.icons()['64'],
            absolutify(self.webapp.get_icon_url(64)))
        eq_(self.product.description(), self.webapp.description)
        eq_(self.product.application_size(),
            self.webapp.current_version.all_files[0].size)
        eq_(self.product.simulation(), None)

        product_data = self.product.product_data(self.contribution)
        eq_(product_data['contrib_uuid'], self.contribution.uuid)
        eq_(product_data['public_id'], self.public_id)
        eq_(product_data['webapp_id'], self.product.webapp().pk)
        eq_(product_data['application_size'], self.product.application_size())

    @override_settings(AMO_LANGUAGES=('en-US', 'es', 'fr'))
    def test_localized_properties(self):
        en_name = unicode(self.webapp.name)
        en_desc = unicode(self.webapp.description)
        loc_names = {
            'fr': 'Le Vaurien',
            'es': 'El Mocoso',
        }
        loc_desc = {
            'fr': u"ceci est une description d'application",
            'es': u'se trata de una descripción de la aplicación',
        }
        self.webapp.name = loc_names
        self.webapp.description = loc_desc
        self.webapp.save()

        names = self.product.localized_properties()
        eq_(names['es']['name'], loc_names['es'])
        eq_(names['es']['description'], loc_desc['es'])
        eq_(names['fr']['name'], loc_names['fr'])
        eq_(names['fr']['description'], loc_desc['fr'])
        eq_(names['en-US']['name'], en_name)
        eq_(names['en-US']['description'], en_desc)


@override_settings(PAYMENT_PROVIDERS=['bango', 'reference'])
class TestWebAppProductMultipleProviders(BaseTestWebAppProduct):
    def setUp(self):
        super(TestWebAppProductMultipleProviders, self).setUp()
        account = PaymentAccount.objects.create(
            user=self.user, uri='foo', name='test', inactive=False,
            solitude_seller=self.seller, account_id=321, seller_uri='abc',
            provider=PROVIDER_REFERENCE)
        WebappPaymentAccount.objects.create(
            webapp=self.webapp, account_uri='foo',
            payment_account=account, product_uri='newuri')

    def test_webapp_product_multiple_providers(self):
        product_data = self.product.product_data(self.contribution)
        eq_(product_data['contrib_uuid'], self.contribution.uuid)
        eq_(product_data['public_id'], self.public_id)
        eq_(product_data['webapp_id'], self.product.webapp().pk)
        eq_(product_data['application_size'],
            self.product.application_size())


class TestInAppProduct(InAppPurchaseTest):

    def setUp(self):
        super(TestInAppProduct, self).setUp()
        self.contribution = Contribution.objects.create(
            user=self.user,
            webapp=self.webapp,
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
        eq_(self.product.webapp(), self.inapp.webapp)
        eq_(self.product.price(), self.inapp.price)
        eq_(self.product.icons()[64], absolutify(self.inapp.logo_url))
        eq_(self.product.description(), self.inapp.webapp.description)
        eq_(self.product.application_size(), None)
        eq_(self.product.simulation(), None)

        product_data = self.product.product_data(self.contribution)
        eq_(product_data['contrib_uuid'], self.contribution.uuid)
        eq_(product_data['webapp_id'], self.product.webapp().pk)
        eq_(product_data['inapp_id'], self.product.id())
        eq_(product_data['application_size'], self.product.application_size())
        eq_(product_data['public_id'], self.public_id)

    def test_no_url(self):
        self.inapp.logo_url = None
        with self.settings(MEDIA_URL='/media/'):
            eq_(self.product.icons()[64],
                'http://testserver/media/img/mkt/icons/rocket-64.png')

    def test_no_user(self):
        product_data = self.product.product_data(self.contribution)
        ok_('buyer_email' not in product_data)


class TestSimulatedInAppProduct(InAppPurchaseTest):

    def setUp(self):
        super(TestSimulatedInAppProduct, self).setUp()
        self.contribution = Contribution.objects.create()
        self.inapp.webapp = None
        self.inapp.simulate = json.dumps({'result': 'postback'})
        self.inapp.stub = True
        self.inapp.save()
        self.product = SimulatedInAppProduct(self.inapp)

    def test_inapp_product(self):
        eq_(self.product.id(), self.inapp.pk)
        eq_(self.product.name(), unicode(self.inapp.name))
        eq_(self.product.webapp(), None)
        eq_(self.product.price(), self.inapp.price)
        eq_(self.product.icons()[64], absolutify(self.inapp.logo_url))
        eq_(self.product.application_size(), None)
        eq_(self.product.description(),
            'This is a stub product for testing only')
        eq_(self.product.simulation(), {'result': 'postback'})

        product_data = self.product.product_data(self.contribution)
        eq_(product_data['contrib_uuid'], self.contribution.uuid)
        eq_(product_data['inapp_id'], self.product.id())
        eq_(product_data['application_size'], self.product.application_size())
