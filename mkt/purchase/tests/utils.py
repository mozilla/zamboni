from decimal import Decimal

import amo.tests
from addons.models import Addon
from market.models import AddonPremium, Price, PriceCurrency
from mkt.inapp.models import InAppProduct
from mkt.developers.models import (AddonPaymentAccount, PaymentAccount,
                                   SolitudeSeller)
from mkt.site.fixtures import fixture
from users.models import UserProfile


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


class InAppPurchaseTest(PurchaseTest):

    def setUp(self):
        super(InAppPurchaseTest, self).setUp()
        self.inapp = InAppProduct.objects.create(
            logo_url='logo.png', name='Inapp Object', price=self.price,
            webapp=self.addon)
