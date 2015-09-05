from decimal import Decimal

import mock

import mkt
from mkt.developers.models import (WebappPaymentAccount, PaymentAccount,
                                   SolitudeSeller)
from mkt.inapp.models import InAppProduct
from mkt.prices.models import WebappPremium, Price, PriceCurrency
from mkt.site.fixtures import fixture
from mkt.site.tests import TestCase
from mkt.users.models import UserProfile
from mkt.webapps.models import Webapp


class PurchaseTest(TestCase):
    fixtures = fixture('prices', 'user_admin', 'user_999', 'webapp_337141')

    def setUp(self):
        self.setup_base()
        self.login('regular@mozilla.com')
        self.user = UserProfile.objects.get(email='regular@mozilla.com')
        self.brl = PriceCurrency.objects.create(currency='BRL',
                                                price=Decimal('0.5'),
                                                tier_id=1)
        self.setup_package()
        self.setup_mock_generic_product()
        self.setup_public_id()

    def setup_base(self):
        self.webapp = Webapp.objects.get(pk=337141)
        self.webapp.update(premium_type=mkt.WEBAPP_PREMIUM)
        self.price = Price.objects.get(pk=1)
        WebappPremium.objects.create(webapp=self.webapp, price=self.price)

        # Refetch webapp from the database to populate webapp.premium field.
        self.webapp = Webapp.objects.get(pk=self.webapp.pk)

    def setup_package(self):
        self.seller = SolitudeSeller.objects.create(
            resource_uri='/path/to/sel', uuid='seller-id', user=self.user)
        self.account = PaymentAccount.objects.create(
            user=self.user, uri='asdf', name='test', inactive=False,
            solitude_seller=self.seller, account_id=123)
        WebappPaymentAccount.objects.create(
            webapp=self.webapp, account_uri='foo',
            payment_account=self.account, product_uri='bpruri')

    def setup_mock_generic_product(self):
        patched_product = mock.patch(
            'mkt.developers.providers.Provider.generic')
        self.mock_product = patched_product.start()
        self.addCleanup(patched_product.stop)

    def setup_public_id(self):
        self.public_id = 'public-id-set-in-devhub'
        self.webapp.update(solitude_public_id=self.public_id)


class InAppPurchaseTest(PurchaseTest):

    def setup_base(self):
        super(InAppPurchaseTest, self).setup_base()
        self.inapp = InAppProduct.objects.create(
            logo_url='logo.png', name=u'Ivan Krsti\u0107',
            price=self.price, webapp=self.webapp)
