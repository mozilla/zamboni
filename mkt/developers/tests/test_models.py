from datetime import datetime, timedelta

from django.test.utils import override_settings

from mock import Mock, patch
from nose.tools import eq_, ok_

import mkt
import mkt.site.tests
from mkt.constants.payments import PROVIDER_BANGO, PROVIDER_REFERENCE
from mkt.developers.models import (ActivityLog, AddonPaymentAccount,
                                   CantCancel, PaymentAccount,
                                   SolitudeSeller)
from mkt.developers.providers import get_provider
from mkt.site.fixtures import fixture
from mkt.users.models import UserProfile
from mkt.webapps.models import Webapp

from .test_providers import Patcher


class TestActivityLogCount(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141', 'user_2519')

    def setUp(self):
        now = datetime.now()
        bom = datetime(now.year, now.month, 1)
        self.lm = bom - timedelta(days=1)
        self.user = UserProfile.objects.filter()[0]
        mkt.set_user(self.user)

    def test_not_review_count(self):
        mkt.log(mkt.LOG['EDIT_VERSION'], Webapp.objects.get())
        eq_(len(ActivityLog.objects.monthly_reviews()), 0)

    def test_review_count(self):
        mkt.log(mkt.LOG['APPROVE_VERSION'], Webapp.objects.get())
        result = ActivityLog.objects.monthly_reviews()
        eq_(len(result), 1)
        eq_(result[0]['approval_count'], 1)
        eq_(result[0]['user'], self.user.pk)

    def test_review_count_few(self):
        for x in range(0, 5):
            mkt.log(mkt.LOG['APPROVE_VERSION'], Webapp.objects.get())
        result = ActivityLog.objects.monthly_reviews()
        eq_(len(result), 1)
        eq_(result[0]['approval_count'], 5)

    def test_review_last_month(self):
        log = mkt.log(mkt.LOG['APPROVE_VERSION'], Webapp.objects.get())
        log.update(created=self.lm)
        eq_(len(ActivityLog.objects.monthly_reviews()), 0)

    def test_not_total(self):
        mkt.log(mkt.LOG['EDIT_VERSION'], Webapp.objects.get())
        eq_(len(ActivityLog.objects.total_reviews()), 0)

    def test_total_few(self):
        for x in range(0, 5):
            mkt.log(mkt.LOG['APPROVE_VERSION'], Webapp.objects.get())
        result = ActivityLog.objects.total_reviews()
        eq_(len(result), 1)
        eq_(result[0]['approval_count'], 5)

    def test_total_last_month(self):
        log = mkt.log(mkt.LOG['APPROVE_VERSION'], Webapp.objects.get())
        log.update(created=self.lm)
        result = ActivityLog.objects.total_reviews()
        eq_(len(result), 1)
        eq_(result[0]['approval_count'], 1)
        eq_(result[0]['user'], self.user.pk)

    def test_log_admin(self):
        mkt.log(mkt.LOG['OBJECT_EDITED'], Webapp.objects.get())
        eq_(len(ActivityLog.objects.admin_events()), 1)
        eq_(len(ActivityLog.objects.for_developer()), 0)

    def test_log_not_admin(self):
        mkt.log(mkt.LOG['EDIT_VERSION'], Webapp.objects.get())
        eq_(len(ActivityLog.objects.admin_events()), 0)
        eq_(len(ActivityLog.objects.for_developer()), 1)


@override_settings(DEFAULT_PAYMENT_PROVIDER='bango',
                   PAYMENT_PROVIDERS=['bango'])
class TestPaymentAccount(Patcher, mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141', 'user_999')

    def setUp(self):
        self.user = UserProfile.objects.filter()[0]
        self.seller, self.solsel = self.create_solitude_seller()
        super(TestPaymentAccount, self).setUp()

    def create_solitude_seller(self, **kwargs):
        solsel_patcher = patch('mkt.developers.models.SolitudeSeller.create')
        solsel = solsel_patcher.start()
        seller_params = {'resource_uri': 'selleruri', 'user': self.user}
        seller_params.update(kwargs)
        seller = SolitudeSeller.objects.create(**seller_params)
        solsel.return_value = seller
        solsel.patcher = solsel_patcher
        return seller, solsel

    def tearDown(self):
        self.solsel.patcher.stop()
        super(TestPaymentAccount, self).tearDown()

    def test_create_bango(self):
        # Return a seller object without hitting Bango.
        self.bango_patcher.package.post.return_value = {
            'resource_uri': 'zipzap',
            'package_id': 123,
        }

        res = get_provider().account_create(
            self.user, {'account_name': 'Test Account'})
        eq_(res.name, 'Test Account')
        eq_(res.user, self.user)
        eq_(res.seller_uri, 'selleruri')
        eq_(res.account_id, 123)
        eq_(res.uri, 'zipzap')

        self.bango_patcher.package.post.assert_called_with(
            data={'paypalEmailAddress': 'nobody@example.com',
                  'seller': 'selleruri'})

        self.bango_patcher.bank.post.assert_called_with(
            data={'seller_bango': 'zipzap'})

    def test_cancel(self):
        res = PaymentAccount.objects.create(
            name='asdf', user=self.user, uri='foo', seller_uri='uri1',
            solitude_seller=self.seller)

        addon = Webapp.objects.get()
        AddonPaymentAccount.objects.create(
            addon=addon, account_uri='foo',
            payment_account=res, product_uri='bpruri')

        assert addon.reload().status != mkt.STATUS_NULL
        res.cancel(disable_refs=True)
        assert res.inactive
        assert addon.reload().status == mkt.STATUS_NULL
        assert not AddonPaymentAccount.objects.exists()

    def test_cancel_shared(self):
        res = PaymentAccount.objects.create(
            name='asdf', user=self.user, uri='foo',
            solitude_seller=self.seller, shared=True)

        addon = Webapp.objects.get()
        AddonPaymentAccount.objects.create(
            addon=addon, account_uri='foo',
            payment_account=res, product_uri='bpruri')

        with self.assertRaises(CantCancel):
            res.cancel()

    def test_cancel_multiple_accounts(self):
        acct1 = PaymentAccount.objects.create(
            name='asdf', user=self.user, uri='foo', seller_uri='uri1',
            solitude_seller=self.seller, provider=PROVIDER_BANGO)
        acct2 = PaymentAccount.objects.create(
            name='fdsa', user=self.user, uri='bar', seller_uri='uri2',
            solitude_seller=self.seller, provider=PROVIDER_REFERENCE)

        addon = Webapp.objects.get(pk=337141)
        AddonPaymentAccount.objects.create(
            addon=addon, account_uri='foo',
            payment_account=acct1, product_uri='bpruri')
        still_around = AddonPaymentAccount.objects.create(
            addon=addon, account_uri='bar',
            payment_account=acct2, product_uri='asiuri')

        ok_(addon.reload().status != mkt.STATUS_NULL)
        acct1.cancel(disable_refs=True)
        ok_(acct1.inactive)
        ok_(addon.reload().status != mkt.STATUS_NULL)
        pks = AddonPaymentAccount.objects.values_list('pk', flat=True)
        eq_(len(pks), 1)
        eq_(pks[0], still_around.pk)

    def test_get_details(self):
        package = Mock()
        package.get.return_value = {'full': {'vendorName': 'a',
                                             'some_other_value': 'b'}}
        self.bango_patcher.package.return_value = package

        res = PaymentAccount.objects.create(
            name='asdf', user=self.user, uri='/foo/bar/123',
            solitude_seller=self.seller)

        deets = res.get_provider().account_retrieve(res)
        eq_(deets['account_name'], res.name)
        eq_(deets['vendorName'], 'a')
        assert 'some_other_value' not in deets

        self.bango_patcher.package.assert_called_with('123')
        package.get.assert_called_with(data={'full': True})

    def test_update_account_details(self):
        res = PaymentAccount.objects.create(
            name='asdf', user=self.user, uri='foo',
            solitude_seller=self.seller)

        res.get_provider().account_update(res, {
            'account_name': 'new name',
            'vendorName': 'new vendor name',
            'something_other_value': 'not a package key'
        })
        eq_(res.name, 'new name')

        self.bango_patcher.api.by_url(res.uri).patch.assert_called_with(
            data={'vendorName': 'new vendor name'})
