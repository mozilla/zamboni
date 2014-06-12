from decimal import Decimal

import mock

import amo.tests
from mkt.developers.models import (AddonPaymentAccount, PaymentAccount,
                                   SolitudeSeller)
from mkt.inapp.models import InAppProduct
from mkt.prices.models import AddonPremium, Price, PriceCurrency
from mkt.site.fixtures import fixture
from mkt.webapps.models import Addon
from mkt.users.models import UserProfile


class PurchaseTest(amo.tests.TestCase):
    fixtures = fixture('prices', 'user_admin', 'user_999', 'webapp_337141')

    def setUp(self):
        self.setup_base()
        assert self.client.login(username='regular@mozilla.com',
                                 password='password')
        self.user = UserProfile.objects.get(email='regular@mozilla.com')
        self.brl = PriceCurrency.objects.create(currency='BRL',
                                                price=Decimal('0.5'),
                                                tier_id=1)
        self.setup_package()
        self.setup_mock_generic_product()
        self.setup_public_id()

    def setup_base(self):
        self.addon = Addon.objects.get(pk=337141)
        self.addon.update(premium_type=amo.ADDON_PREMIUM)
        self.price = Price.objects.get(pk=1)
        AddonPremium.objects.create(addon=self.addon, price=self.price)

        # Refetch addon from the database to populate addon.premium field.
        self.addon = Addon.objects.get(pk=self.addon.pk)

    def setup_package(self):
        self.seller = SolitudeSeller.objects.create(
            resource_uri='/path/to/sel', uuid='seller-id', user=self.user)
        self.account = PaymentAccount.objects.create(
            user=self.user, uri='asdf', name='test', inactive=False,
            solitude_seller=self.seller, account_id=123)
        AddonPaymentAccount.objects.create(
            addon=self.addon, account_uri='foo',
            payment_account=self.account, product_uri='bpruri')

    def setup_mock_generic_product(self):
        patched_product = mock.patch(
            'mkt.developers.providers.Provider.generic')
        self.mock_product = patched_product.start()
        self.addCleanup(patched_product.stop)

    def setup_public_id(self):
        self.public_id = 'public-id-set-in-devhub'
        self.addon.update(solitude_public_id=self.public_id)


class InAppPurchaseTest(PurchaseTest):

    def setup_base(self):
        super(InAppPurchaseTest, self).setup_base()
        self.inapp = InAppProduct.objects.create(
            logo_url='logo.png', name='Inapp Object', price=self.price,
            webapp=self.addon)
