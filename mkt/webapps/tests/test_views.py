from django.contrib.auth.models import AnonymousUser
from django.core.urlresolvers import reverse
from django.test.client import RequestFactory

from nose.tools import eq_, ok_

import mkt.site.tests
from mkt.api.tests.test_oauth import BaseOAuth
from mkt.constants import APP_FEATURES
from mkt.constants.payments import PROVIDER_BANGO, PROVIDER_REFERENCE
from mkt.developers.models import (AddonPaymentAccount, PaymentAccount,
                                   SolitudeSeller)
from mkt.site.fixtures import fixture
from mkt.site.tests import user_factory
from mkt.webapps.models import Webapp
from mkt.webapps.serializers import (AppFeaturesSerializer, AppSerializer,
                                     SimpleAppSerializer)


class TestAppFeaturesSerializer(BaseOAuth):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        self.features = Webapp.objects.get(pk=337141).latest_version.features
        self.request = RequestFactory().get('/')
        self.request.user = AnonymousUser()

    def get_native(self, **kwargs):
        self.features.update(**kwargs)
        return AppFeaturesSerializer().to_native(self.features)

    def test_no_features(self):
        native = self.get_native()
        ok_(not native['required'])

    def test_one_feature(self):
        native = self.get_native(has_pay=True)
        self.assertSetEqual(native['required'], ['pay'])

    def test_all_features(self):
        data = dict(('has_' + f.lower(), True) for f in APP_FEATURES)
        native = self.get_native(**data)
        self.assertSetEqual(native['required'],
                            [f.lower() for f in APP_FEATURES])


class TestSimpleAppSerializer(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        self.webapp = Webapp.objects.get(pk=337141)
        self.request = RequestFactory().get('/')
        self.request.user = AnonymousUser()

    def app(self):
        return AppSerializer(self.webapp,
                             context={'request': self.request})

    def simple_app(self):
        return SimpleAppSerializer(self.webapp,
                                   context={'request': self.request})

    def add_pay_account(self, provider=PROVIDER_BANGO):
        user = user_factory()
        acct = PaymentAccount.objects.create(
            solitude_seller=SolitudeSeller.objects.create(user=user),
            provider=provider, user=user)
        AddonPaymentAccount.objects.create(addon=self.webapp,
                                           payment_account=acct)
        return acct

    def test_regions_present(self):
        # Regression test for bug 964802.
        data = self.simple_app().data
        ok_('regions' in data)
        eq_(len(data['regions']), len(self.webapp.get_regions()))

    def test_no_payment_account_when_not_premium(self):
        eq_(self.app().data['payment_account'], None)

    def test_no_payment_account(self):
        self.make_premium(self.webapp)
        eq_(self.app().data['payment_account'], None)

    def test_no_bango_account(self):
        self.make_premium(self.webapp)
        self.add_pay_account(provider=PROVIDER_REFERENCE)
        eq_(self.app().data['payment_account'], None)

    def test_payment_account(self):
        self.make_premium(self.webapp)
        acct = self.add_pay_account()
        eq_(self.app().data['payment_account'],
            reverse('payment-account-detail', args=[acct.pk]))
