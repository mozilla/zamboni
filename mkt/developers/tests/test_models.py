from datetime import datetime, timedelta
from os import path

from django.core.urlresolvers import NoReverseMatch
from django.test.utils import override_settings

from mock import Mock, patch
from nose.tools import eq_, ok_

import amo
import amo.tests
from mkt.constants.payments import PROVIDER_BANGO, PROVIDER_BOKU
from mkt.developers.models import (ActivityLog, ActivityLogAttachment,
                                   AddonPaymentAccount, CantCancel,
                                   PaymentAccount, PreloadTestPlan,
                                   SolitudeSeller)
from mkt.developers.providers import get_provider
from mkt.site.fixtures import fixture
from mkt.users.models import UserProfile
from mkt.webapps.models import Addon, Webapp
from .test_providers import Patcher


TEST_PATH = path.dirname(path.abspath(__file__))
ATTACHMENTS_DIR = path.abspath(path.join(TEST_PATH, '..', '..', 'comm',
                                         'tests', 'attachments'))


class TestActivityLogCount(amo.tests.TestCase):
    fixtures = fixture('webapp_337141', 'user_2519')

    def setUp(self):
        now = datetime.now()
        bom = datetime(now.year, now.month, 1)
        self.lm = bom - timedelta(days=1)
        self.user = UserProfile.objects.filter()[0]
        amo.set_user(self.user)

    def test_not_review_count(self):
        amo.log(amo.LOG['EDIT_VERSION'], Webapp.objects.get())
        eq_(len(ActivityLog.objects.monthly_reviews()), 0)

    def test_review_count(self):
        amo.log(amo.LOG['APPROVE_VERSION'], Webapp.objects.get())
        result = ActivityLog.objects.monthly_reviews()
        eq_(len(result), 1)
        eq_(result[0]['approval_count'], 1)
        eq_(result[0]['user'], self.user.pk)

    def test_review_count_few(self):
        for x in range(0, 5):
            amo.log(amo.LOG['APPROVE_VERSION'], Webapp.objects.get())
        result = ActivityLog.objects.monthly_reviews()
        eq_(len(result), 1)
        eq_(result[0]['approval_count'], 5)

    def test_review_last_month(self):
        log = amo.log(amo.LOG['APPROVE_VERSION'], Webapp.objects.get())
        log.update(created=self.lm)
        eq_(len(ActivityLog.objects.monthly_reviews()), 0)

    def test_not_total(self):
        amo.log(amo.LOG['EDIT_VERSION'], Webapp.objects.get())
        eq_(len(ActivityLog.objects.total_reviews()), 0)

    def test_total_few(self):
        for x in range(0, 5):
            amo.log(amo.LOG['APPROVE_VERSION'], Webapp.objects.get())
        result = ActivityLog.objects.total_reviews()
        eq_(len(result), 1)
        eq_(result[0]['approval_count'], 5)

    def test_total_last_month(self):
        log = amo.log(amo.LOG['APPROVE_VERSION'], Webapp.objects.get())
        log.update(created=self.lm)
        result = ActivityLog.objects.total_reviews()
        eq_(len(result), 1)
        eq_(result[0]['approval_count'], 1)
        eq_(result[0]['user'], self.user.pk)

    def test_log_admin(self):
        amo.log(amo.LOG['OBJECT_EDITED'], Webapp.objects.get())
        eq_(len(ActivityLog.objects.admin_events()), 1)
        eq_(len(ActivityLog.objects.for_developer()), 0)

    def test_log_not_admin(self):
        amo.log(amo.LOG['EDIT_VERSION'], Webapp.objects.get())
        eq_(len(ActivityLog.objects.admin_events()), 0)
        eq_(len(ActivityLog.objects.for_developer()), 1)


class TestPaymentAccount(Patcher, amo.tests.TestCase):
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

        addon = Addon.objects.get()
        AddonPaymentAccount.objects.create(
            addon=addon, account_uri='foo',
            payment_account=res, product_uri='bpruri')

        assert addon.reload().status != amo.STATUS_NULL
        res.cancel(disable_refs=True)
        assert res.inactive
        assert addon.reload().status == amo.STATUS_NULL
        assert not AddonPaymentAccount.objects.exists()

    def test_cancel_shared(self):
        res = PaymentAccount.objects.create(
            name='asdf', user=self.user, uri='foo',
            solitude_seller=self.seller, shared=True)

        addon = Addon.objects.get()
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
            solitude_seller=self.seller, provider=PROVIDER_BOKU)

        addon = Addon.objects.get(pk=337141)
        AddonPaymentAccount.objects.create(
            addon=addon, account_uri='foo',
            payment_account=acct1, product_uri='bpruri')
        still_around = AddonPaymentAccount.objects.create(
            addon=addon, account_uri='bar',
            payment_account=acct2, product_uri='asiuri')

        ok_(addon.reload().status != amo.STATUS_NULL)
        acct1.cancel(disable_refs=True)
        ok_(acct1.inactive)
        ok_(addon.reload().status != amo.STATUS_NULL)
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


@override_settings(REVIEWER_ATTACHMENTS_PATH=ATTACHMENTS_DIR)
class TestActivityLogAttachment(amo.tests.TestCase):
    fixtures = fixture('webapp_337141')

    XSS_STRING = 'MMM <script>alert(bacon);</script>'

    def setUp(self):
        self.user = self._user()
        addon = Addon.objects.get(pk=337141)
        version = addon.latest_version
        al = amo.log(amo.LOG.COMMENT_VERSION, addon, version, user=self.user)
        self.attachment1, self.attachment2 = self._attachments(al)

    def tearDown(self):
        amo.set_user(None)

    def _user(self):
        """Create and return a user"""
        u = UserProfile.objects.create(username='porkbelly')
        amo.set_user(u)
        return u

    def _attachments(self, activity_log):
        """
        Create and return a tuple of ActivityLogAttachment instances.
        """
        ala1 = ActivityLogAttachment.objects.create(
            activity_log=activity_log, filepath='bacon.txt',
            mimetype='text/plain')
        ala2 = ActivityLogAttachment.objects.create(
            activity_log=activity_log, filepath='bacon.jpg',
            description=self.XSS_STRING, mimetype='image/jpeg')
        return ala1, ala2

    def test_filename(self):
        msg = ('ActivityLogAttachment().filename() returning '
               'incorrect filename.')
        eq_(self.attachment1.filename(), 'bacon.txt', msg)
        eq_(self.attachment2.filename(), 'bacon.jpg', msg)

    def test_full_path_dirname(self):
        msg = ('ActivityLogAttachment().full_path() returning incorrect path.')
        FAKE_PATH = '/tmp/attachments/'
        with self.settings(REVIEWER_ATTACHMENTS_PATH=FAKE_PATH):
            eq_(self.attachment1.full_path(), FAKE_PATH + 'bacon.txt', msg)
            eq_(self.attachment2.full_path(), FAKE_PATH + 'bacon.jpg', msg)

    def test_display_name(self):
        msg = ('ActivityLogAttachment().display_name() returning '
               'incorrect display name.')
        eq_(self.attachment1.display_name(), 'bacon.txt', msg)

    def test_display_name_xss(self):
        self.assertNotIn('<script>', self.attachment2.display_name())

    def test_is_image(self):
        msg = ('ActivityLogAttachment().is_image() not correctly detecting '
               'images.')
        eq_(self.attachment1.is_image(), False, msg)
        eq_(self.attachment2.is_image(), True, msg)

    def test_get_absolute_url(self):
        msg = ('ActivityLogAttachment().get_absolute_url() raising a '
               'NoReverseMatch exception.')
        try:
            self.attachment1.get_absolute_url()
            self.attachment2.get_absolute_url()
        except NoReverseMatch:
            assert False, msg


class TestPreloadTestPlan(amo.tests.TestCase):

    def setUp(self):
        self.app = amo.tests.app_factory()
        self.preload = self.app.preloadtestplan_set.create(filename='test.pdf')

    def test_delete_cascade(self):
        eq_(self.preload.addon, self.app)
        self.app.delete()
        eq_(PreloadTestPlan.objects.count(), 0)
