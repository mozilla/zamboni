import json
from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.test.client import RequestFactory
from django.utils.http import urlquote

import mock
from babel import numbers
from nose.tools import eq_, ok_
from pyquery import PyQuery as pq
from slumber import exceptions

import mkt
import mkt.site.tests
from mkt.abuse.models import AbuseReport
from mkt.access.models import Group, GroupUser
from mkt.constants.applications import DEVICE_GAIA
from mkt.constants.payments import (FAILED, PENDING, PROVIDER_BANGO,
                                    PROVIDER_REFERENCE,
                                    SOLITUDE_REFUND_STATUSES)
from mkt.developers.models import (ActivityLog, AddonPaymentAccount,
                                   PaymentAccount, SolitudeSeller)
from mkt.developers.providers import get_provider
from mkt.developers.tests.test_views_payments import (setup_payment_account,
                                                      TEST_PACKAGE_ID)
from mkt.lookup.views import (_transaction_summary, app_summary,
                              transaction_refund, user_delete, user_summary)
from mkt.prices.models import AddonPaymentData, Refund
from mkt.purchase.models import Contribution
from mkt.reviewers.models import QUEUE_TARAKO
from mkt.site.fixtures import fixture
from mkt.site.tests import (ESTestCase, req_factory_factory, TestCase,
                            user_factory)
from mkt.site.utils import app_factory, file_factory, version_factory
from mkt.tags.models import Tag
from mkt.users.models import UserProfile
from mkt.webapps.models import AddonUser, Webapp
from mkt.websites.utils import website_factory


class SummaryTest(TestCase):

    def add_payment_accounts(self, providers, app=None):
        if not app:
            app = self.app
        user = self.user
        seller = SolitudeSeller.objects.create(user=user, uuid='seller-uid')
        for provider in providers:
            uri = 'seller-{p}'.format(p=provider)
            payment = PaymentAccount.objects.create(
                user=user, solitude_seller=seller,
                provider=provider,
                seller_uri=uri, uri=uri,
                agreed_tos=True, account_id='not-important')
            AddonPaymentAccount.objects.create(
                addon=app,
                product_uri='product-{p}'.format(p=provider),
                account_uri=payment.uri,
                payment_account=payment
            )

        app.save()

    def verify_bango_portal(self, app, response):
        bango = pq(response.content)('[data-provider-name=bango]')
        heading = pq('dt', bango).text()
        assert 'Bango' in heading, heading
        assert unicode(app.name) in heading, heading
        eq_(pq('dd a', bango).attr('href'),
            get_provider(name='bango').get_portal_url(app.app_slug))


@mock.patch.object(settings, 'TASK_USER_ID', 999)
class TestAcctSummary(SummaryTest):
    fixtures = fixture('user_support_staff', 'user_999', 'webapp_337141',
                       'user_operator')

    def setUp(self):
        super(TestAcctSummary, self).setUp()
        self.user = UserProfile.objects.get(email='steamcube@mozilla.com')
        self.steamcube = Webapp.objects.get(pk=337141)
        self.otherapp = app_factory(app_slug='otherapp')
        self.reg_user = UserProfile.objects.get(email='regular@mozilla.com')
        self.summary_url = reverse('lookup.user_summary', args=[self.user.pk])
        self.login(UserProfile.objects.get(email='support-staff@mozilla.com'))

    def buy_stuff(self, contrib_type):
        for i in range(3):
            if i == 1:
                curr = 'GBR'
            else:
                curr = 'USD'
            amount = Decimal('2.00')
            Contribution.objects.create(addon=self.steamcube,
                                        type=contrib_type,
                                        currency=curr,
                                        amount=amount,
                                        user_id=self.user.pk)

    def summary(self, expected_status=200):
        res = self.client.get(self.summary_url)
        eq_(res.status_code, expected_status)
        return res

    def payment_data(self):
        return {'full_name': 'Ed Peabody Jr.',
                'business_name': 'Mr. Peabody',
                'phone': '(1) 773-111-2222',
                'address_one': '1111 W Leland Ave',
                'address_two': 'Apt 1W',
                'city': 'Chicago',
                'post_code': '60640',
                'country': 'USA',
                'state': 'Illinois'}

    def test_home_auth(self):
        self.client.logout()
        res = self.client.get(reverse('lookup.home'))
        self.assertLoginRedirects(res, reverse('lookup.home'))

    def test_summary_auth(self):
        self.client.logout()
        res = self.client.get(self.summary_url)
        self.assertLoginRedirects(res, self.summary_url)

    def test_home(self):
        res = self.client.get(reverse('lookup.home'))
        self.assertNoFormErrors(res)
        eq_(res.status_code, 200)

    def test_basic_summary(self):
        res = self.summary()
        eq_(res.context['account'].pk, self.user.pk)

    @mock.patch.object(settings, 'PAYMENT_PROVIDERS', ['bango', 'reference'])
    def test_multiple_payment_accounts(self):
        app = self.steamcube
        self.add_payment_accounts([PROVIDER_BANGO, PROVIDER_REFERENCE],
                                  app=app)
        res = self.summary()
        self.verify_bango_portal(app, res)

    def test_app_counts(self):
        self.buy_stuff(mkt.CONTRIB_PURCHASE)
        sm = self.summary().context['app_summary']
        eq_(sm['app_total'], 3)
        eq_(sm['app_amount']['USD'], Decimal('4.0'))
        eq_(sm['app_amount']['GBR'], Decimal('2.0'))

    def test_requested_refunds(self):
        contrib = Contribution.objects.create(type=mkt.CONTRIB_PURCHASE,
                                              user_id=self.user.pk,
                                              addon=self.steamcube,
                                              currency='USD',
                                              amount='0.99')
        Refund.objects.create(contribution=contrib, user=self.user)
        res = self.summary()
        eq_(res.context['refund_summary']['requested'], 1)
        eq_(res.context['refund_summary']['approved'], 0)

    def test_approved_refunds(self):
        contrib = Contribution.objects.create(type=mkt.CONTRIB_PURCHASE,
                                              user_id=self.user.pk,
                                              addon=self.steamcube,
                                              currency='USD',
                                              amount='0.99')
        Refund.objects.create(contribution=contrib,
                              status=mkt.REFUND_APPROVED_INSTANT,
                              user=self.user)
        res = self.summary()
        eq_(res.context['refund_summary']['requested'], 1)
        eq_(res.context['refund_summary']['approved'], 1)

    def test_app_created(self):
        res = self.summary()
        # Number of apps/add-ons belonging to this user.
        eq_(len(res.context['user_addons']), 1)

    def test_payment_data(self):
        payment_data = self.payment_data()
        AddonPaymentData.objects.create(addon=self.steamcube,
                                        **payment_data)
        res = self.summary()
        pd = res.context['payment_data'][0]
        for key, value in payment_data.iteritems():
            eq_(pd[key], value)

    def test_no_payment_data(self):
        res = self.summary()
        eq_(len(res.context['payment_data']), 0)

    def test_no_duplicate_payment_data(self):
        role = AddonUser.objects.create(user=self.user,
                                        addon=self.otherapp,
                                        role=mkt.AUTHOR_ROLE_DEV)
        self.otherapp.addonuser_set.add(role)
        payment_data = self.payment_data()
        AddonPaymentData.objects.create(addon=self.steamcube,
                                        **payment_data)
        AddonPaymentData.objects.create(addon=self.otherapp,
                                        **payment_data)
        res = self.summary()
        eq_(len(res.context['payment_data']), 1)
        pd = res.context['payment_data'][0]
        for key, value in payment_data.iteritems():
            eq_(pd[key], value)

    def test_operator_app_lookup_only(self):
        GroupUser.objects.create(
            group=Group.objects.get(name='Operators'),
            user=UserProfile.objects.get(email='support-staff@mozilla.com'))
        res = self.client.get(reverse('lookup.home'))
        doc = pq(res.content)
        eq_(doc('#app-search-form select').length, 0)

    def test_delete_user(self):
        staff = UserProfile.objects.get(email='support-staff@mozilla.com')
        req = req_factory_factory(
            reverse('lookup.user_delete', args=[self.user.id]), user=staff,
            post=True, data={'delete_reason': 'basketball reasons'})

        r = user_delete(req, self.user.id)
        self.assert3xx(r, reverse('lookup.user_summary', args=[self.user.id]))

        # Test data.
        assert UserProfile.objects.get(id=self.user.id).deleted
        eq_(staff, ActivityLog.objects.for_user(self.user).filter(
            action=mkt.LOG.DELETE_USER_LOOKUP.id)[0].user)

        # Test frontend.
        req = req_factory_factory(
            reverse('lookup.user_summary', args=[self.user.id]), user=staff)
        r = user_summary(req, self.user.id)
        eq_(r.status_code, 200)
        doc = pq(r.content)
        eq_(doc('#delete-user dd:eq(1)').text(), 'basketball reasons')

    def test_group_list_normal(self):
        staff = UserProfile.objects.get(email='support-staff@mozilla.com')
        GroupUser.objects.create(
            group=Group.objects.get(name='Operators'), user=self.user)
        req = req_factory_factory(self.summary_url, user=staff)
        doc = pq(user_summary(req, self.user.id).content)
        # Test group membership is there.
        eq_(doc('.remove-group td:eq(0)').text(), 'Operators')
        # But no button as support-staff doesn't have admin privs.
        eq_(doc('.remove-group:eq(0)').children().length, 1)

    def test_group_list_admin(self):
        staff = UserProfile.objects.get(email='support-staff@mozilla.com')
        self.grant_permission(staff, 'Admin:%')
        # The existing Operators group will be the first group in the list.
        group = Group.objects.get(name='Operators')
        # Update the name so extra groups don't break the test.
        group.update(name='AA Operators')
        GroupUser.objects.create(group=group, user=self.user)
        # Create a new restricted group that will be second.
        res_group = Group.objects.create(name='AB Restricted', restricted=True)
        GroupUser.objects.create(group=res_group, user=self.user)
        # Update the name so extra groups don't break the test.
        Group.objects.get(name='Support Staff').update(name='AC Support')

        req = req_factory_factory(self.summary_url, user=staff)
        doc = pq(user_summary(req, self.user.id).content)

        # Test normal group membership is there.
        eq_(doc('.remove-group td:eq(0) a').html(), 'AA Operators')
        # Check the remove button is there.
        remove_button = doc('.remove-group td:eq(1) button.remove.button')
        eq_(remove_button.attr('data-api-method'), 'DELETE')
        eq_(remove_button.attr('data-api-group'), str(group.pk))
        eq_(remove_button.attr('data-api-url'),
            reverse('account-groups', kwargs={'pk': self.user.id}))

        # Test restricted group membership is there.
        eq_(doc('.remove-group td').eq(2).text(), 'AB Restricted')
        # Check the remove button is there, but disabled.
        remove_button = doc('.remove-group td:eq(1) button.button.disabled')

        # Test there is a group select - the list is alphabetical.
        eq_(doc('.add-group option').eq(1).text(), 'AA Operators')
        # The restricted group shouldn't be here.
        eq_(doc('.add-group option').eq(2).text(), 'AC Support')
        # And the add button too.
        add_button = doc('.add-group td:eq(1) button.add.button')
        eq_(add_button.attr('data-api-method'), 'POST')
        eq_(add_button.attr('data-api-url'),
            reverse('account-groups', kwargs={'pk': self.user.id}))


class TestBangoRedirect(TestCase):
    fixtures = fixture('user_support_staff', 'user_999', 'webapp_337141',
                       'user_operator')

    def setUp(self):
        super(TestBangoRedirect, self).setUp()
        self.user = UserProfile.objects.get(email='steamcube@mozilla.com')
        self.steamcube = Webapp.objects.get(pk=337141)
        self.otherapp = app_factory(app_slug='otherapp')
        self.reg_user = UserProfile.objects.get(email='regular@mozilla.com')
        self.summary_url = reverse('lookup.user_summary', args=[self.user.pk])
        self.login(UserProfile.objects.get(email='support-staff@mozilla.com'))
        self.steamcube.update(premium_type=mkt.ADDON_PREMIUM)
        self.account = setup_payment_account(self.steamcube, self.user)
        self.portal_url = reverse(
            'lookup.bango_portal_from_package',
            args=[self.account.payment_account.account_id])
        self.authentication_token = u'D0A44686-D4A3-4B2F-9BEB-5E4975E35192'

    @mock.patch('mkt.developers.views_payments.client.api')
    def test_bango_portal_redirect(self, api):
        api.bango.login.post.return_value = {
            'person_id': 600925,
            'email_address': u'admin@place.com',
            'authentication_token': self.authentication_token,
        }
        res = self.client.get(self.portal_url)
        eq_(res.status_code, 302)
        eq_(api.bango.login.post.call_args[0][0]['packageId'],
            int(TEST_PACKAGE_ID))
        redirect_url = res['Location']
        assert self.authentication_token in redirect_url, redirect_url
        assert 'emailAddress=admin%40place.com' in redirect_url, redirect_url

    @mock.patch('mkt.developers.views_payments.client.api')
    def test_bango_portal_redirect_api_error(self, api):
        message = 'Something went wrong.'
        error = {'__all__': [message]}
        api.bango.login.post.side_effect = exceptions.HttpClientError(
            content=error)
        res = self.client.get(self.portal_url, follow=True)
        eq_(res.redirect_chain, [('http://testserver/lookup/', 302)])
        ok_(message in [msg.message for msg in res.context['messages']][0])

    @mock.patch('mkt.developers.views_payments.client.api')
    def test_bango_portal_redirect_role_error(self, api):
        self.login(self.user)
        res = self.client.get(self.portal_url)
        eq_(res.status_code, 403)


class SearchTestMixin(object):

    def search(self, expect_objects=True, **data):
        res = self.client.get(self.url, data)
        eq_(res.status_code, 200)
        data = json.loads(res.content)
        if expect_objects:
            assert len(data['objects']), 'should be more than 0 objects'
        return data

    def test_auth_required(self):
        self.client.logout()
        res = self.client.get(self.url)
        self.assertLoginRedirects(res, self.url)


class TestAcctSearch(TestCase, SearchTestMixin):
    fixtures = fixture('user_10482', 'user_support_staff', 'user_operator')

    def setUp(self):
        super(TestAcctSearch, self).setUp()
        self.url = reverse('lookup.user_search')
        self.user = UserProfile.objects.get(email='clouserw@mozilla.com')
        self.login(UserProfile.objects.get(email='support-staff@mozilla.com'))

    def verify_result(self, data):
        eq_(data['objects'][0]['fxa_uid'], self.user.fxa_uid)
        eq_(data['objects'][0]['display_name'], self.user.display_name)
        eq_(data['objects'][0]['email'], self.user.email)
        eq_(data['objects'][0]['id'], self.user.pk)
        eq_(data['objects'][0]['url'], reverse('lookup.user_summary',
                                               args=[self.user.pk]))

    def test_by_fxa_uid(self):
        self.user.update(fxa_uid='fake-fxa-uid')
        data = self.search(q='fake-fxa-uid')
        self.verify_result(data)

    def test_by_display_name(self):
        self.user.update(display_name='Kumar McMillan')
        data = self.search(q='mcmill')
        self.verify_result(data)

    def test_by_id(self):
        data = self.search(q=self.user.pk)
        self.verify_result(data)

    def test_by_email(self):
        self.user.update(email='fonzi@happydays.com')
        data = self.search(q='fonzi')
        self.verify_result(data)

    @mock.patch('mkt.constants.lookup.SEARCH_LIMIT', 2)
    @mock.patch('mkt.constants.lookup.MAX_RESULTS', 3)
    def test_all_results(self):
        for x in range(4):
            name = 'chr' + str(x)
            user_factory(email=name)

        # Test not at search limit.
        data = self.search(q='clouserw')
        eq_(len(data['objects']), 1)

        # Test search limit.
        data = self.search(q='chr')
        eq_(len(data['objects']), 2)

        # Test maximum search result.
        data = self.search(q='chr', limit='max')
        eq_(len(data['objects']), 3)


class TestTransactionSearch(TestCase):
    fixtures = fixture('user_support_staff', 'user_999', 'user_operator')

    def setUp(self):
        self.uuid = 45
        self.url = reverse('lookup.transaction_search')
        self.login('support-staff@mozilla.com')

    def test_redirect(self):
        r = self.client.get(self.url, {'q': self.uuid})
        self.assert3xx(r, reverse('lookup.transaction_summary',
                                  args=[self.uuid]))

    def test_no_perm(self):
        self.login('regular@mozilla.com')
        r = self.client.get(self.url, {'q': self.uuid})
        eq_(r.status_code, 403)

        self.login('operator@mozilla.com')
        r = self.client.get(self.url, {'q': self.uuid})
        eq_(r.status_code, 403)


class TestTransactionSummary(TestCase):
    fixtures = fixture('user_support_staff', 'user_999', 'user_operator')

    def setUp(self):
        self.uuid = 'some:uuid'
        self.transaction_id = 'some:tr'
        self.seller_uuid = 456
        self.related_tx_uuid = 789
        self.user = UserProfile.objects.get(pk=999)

        self.app = app_factory()
        self.contrib = Contribution.objects.create(
            addon=self.app, uuid=self.uuid, user=self.user,
            transaction_id=self.transaction_id)

        self.url = reverse('lookup.transaction_summary', args=[self.uuid])
        self.login('support-staff@mozilla.com')

    @mock.patch.object(settings, 'TASK_USER_ID', 999)
    def create_test_refund(self):
        refund_contrib = Contribution.objects.create(
            addon=self.app, related=self.contrib, type=mkt.CONTRIB_REFUND,
            transaction_id='testtransactionid', user=self.user)
        refund_contrib.enqueue_refund(mkt.REFUND_PENDING, self.user)

    @mock.patch('mkt.lookup.views.client')
    def test_transaction_summary(self, solitude):
        data = _transaction_summary(self.uuid)

        eq_(data['is_refundable'], False)
        eq_(data['contrib'].pk, self.contrib.pk)

    @mock.patch('mkt.lookup.views.client')
    def test_refund_status(self, solitude):
        solitude.api.bango.refund.get_object_or_404.return_value = (
            {'status': PENDING})
        solitude.api.generic.transaction.get_object_or_404.return_value = (
            {'uid_support': 'foo', 'provider': 2})

        self.create_test_refund()
        data = _transaction_summary(self.uuid)

        eq_(data['support'], 'foo')
        eq_(data['refund_status'], SOLITUDE_REFUND_STATUSES[PENDING])

    @mock.patch('mkt.lookup.views.client')
    def test_bango_transaction_status(self, solitude):
        solitude.api.generic.transaction.get_object_or_404.return_value = (
            {'uid_support': 'foo', 'provider': 1,
             'seller': '/generic/seller/1/'})

        self.create_test_refund()
        data = _transaction_summary(self.uuid)
        ok_(data['package_id'])

    @mock.patch('mkt.lookup.views.client')
    def test_transaction_status(self, solitude):
        solitude.api.generic.transaction.get_object_or_404.return_value = (
            {'uid_support': 'foo', 'provider': 2})

        self.create_test_refund()
        data = _transaction_summary(self.uuid)

        eq_(data['support'], 'foo')
        eq_(data['provider'], 'reference')

    @mock.patch('mkt.lookup.views.client')
    def test_transaction_fails(self, solitude):
        solitude.api.generic.transaction.get_object_or_404.side_effect = (
            ObjectDoesNotExist)

        self.create_test_refund()
        data = _transaction_summary(self.uuid)

        eq_(data['support'], None)
        eq_(data['lookup']['transaction'], False)

    @mock.patch('mkt.lookup.views.client')
    def test_is_refundable(self, solitude):
        solitude.api.bango.refund.get_object_or_404.return_value = (
            {'status': PENDING})

        self.contrib.update(type=mkt.CONTRIB_PURCHASE)
        data = _transaction_summary(self.uuid)
        eq_(data['contrib'].pk, self.contrib.pk)
        eq_(data['is_refundable'], True)

        self.create_test_refund()
        data = _transaction_summary(self.uuid)
        eq_(data['is_refundable'], False)

    @mock.patch('mkt.lookup.views.client')
    def test_200(self, solitude):
        r = self.client.get(self.url)
        eq_(r.status_code, 200)

    def test_no_perm_403(self):
        self.login('regular@mozilla.com')
        r = self.client.get(self.url)
        eq_(r.status_code, 403)

        self.login('operator@mozilla.com')
        r = self.client.get(self.url)
        eq_(r.status_code, 403)

    def test_no_transaction_404(self):
        r = self.client.get(reverse('lookup.transaction_summary', args=[999]))
        eq_(r.status_code, 404)


@mock.patch.object(settings, 'TASK_USER_ID', 999)
class TestTransactionRefund(TestCase):
    fixtures = fixture('user_support_staff', 'user_999')

    def setUp(self):
        self.uuid = 'paymentuuid'
        self.refund_uuid = 'refunduuid'
        self.summary_url = reverse('lookup.transaction_summary',
                                   args=[self.uuid])
        self.url = reverse('lookup.transaction_refund', args=[self.uuid])
        self.app = app_factory()
        self.user = UserProfile.objects.get(email='regular@mozilla.com')
        AddonUser.objects.create(addon=self.app, user=self.user)

        self.req = self.request({'refund_reason': 'text'})
        self.contrib = Contribution.objects.create(
            addon=self.app, user=self.user, uuid=self.uuid,
            type=mkt.CONTRIB_PURCHASE, amount=1, transaction_id='123')
        # Fix Django 1.4 RequestFactory bug with MessageMiddleware.
        setattr(self.req, 'session', 'session')
        messages = FallbackStorage(self.req)
        setattr(self.req, '_messages', messages)
        self.login(self.req.user)

    def bango_ret(self, status):
        return {
            'status': status,
            'transaction': 'transaction_uri',
            'uuid': 'some:uid'
        }

    def request(self, data):
        req = RequestFactory().post(self.url, data)
        req.user = UserProfile.objects.get(email='support-staff@mozilla.com')
        req.groups = req.user.groups.all()
        return req

    def refund_tx_ret(self):
        return {'uuid': self.refund_uuid}

    @mock.patch('mkt.lookup.views.client')
    def test_fake_refund_ignored(self, client):
        req = self.request({'refund_reason': 'text', 'fake': 'OK'})
        with self.settings(BANGO_FAKE_REFUNDS=False):
            transaction_refund(req, self.uuid)
        client.api.bango.refund.post.assert_called_with(
            {'uuid': '123', 'manual': False})

    @mock.patch('mkt.lookup.views.client')
    def test_manual_refund(self, client):
        req = self.request({'refund_reason': 'text', 'manual': True})
        transaction_refund(req, self.uuid)
        client.api.bango.refund.post.assert_called_with(
            {'uuid': '123', 'manual': True})

    @mock.patch('mkt.lookup.views.client')
    def test_fake_refund(self, client):
        req = self.request({'refund_reason': 'text', 'fake': 'OK'})
        with self.settings(BANGO_FAKE_REFUNDS=True):
            transaction_refund(req, self.uuid)
        client.api.bango.refund.post.assert_called_with({
            'fake_response_status': {'responseCode': 'OK'},
            'uuid': '123', 'manual': False})

    @mock.patch('mkt.lookup.views.client')
    def test_refund_success(self, solitude):
        solitude.api.bango.refund.post.return_value = self.bango_ret(PENDING)
        solitude.get.return_value = self.refund_tx_ret()

        # Do refund.
        res = transaction_refund(self.req, self.uuid)
        refund = Refund.objects.filter(contribution__addon=self.app)
        refund_contribs = self.contrib.get_refund_contribs()

        # Check Refund created.
        assert refund.exists()
        eq_(refund[0].status, mkt.REFUND_PENDING)
        assert self.req.POST['refund_reason'] in refund[0].refund_reason

        # Check refund Contribution created.
        eq_(refund_contribs.exists(), True)
        eq_(refund_contribs[0].refund, refund[0])
        eq_(refund_contribs[0].related, self.contrib)
        eq_(refund_contribs[0].amount, -self.contrib.amount)
        eq_(refund_contribs[0].transaction_id, 'some:uid')

        self.assert3xx(res, self.summary_url)

    @mock.patch('mkt.lookup.views.client')
    def test_refund_failed(self, solitude):
        solitude.api.bango.refund.post.return_value = self.bango_ret(FAILED)

        res = transaction_refund(self.req, self.uuid)

        # Check no refund Contributions created.
        assert not self.contrib.get_refund_contribs().exists()
        self.assert3xx(res, self.summary_url)

    def test_cant_refund(self):
        self.contrib.update(type=mkt.CONTRIB_PENDING)
        resp = self.client.post(self.url, {'refund_reason': 'text'})
        eq_(resp.status_code, 404)

    @mock.patch('mkt.lookup.views.client')
    def test_already_refunded(self, solitude):
        solitude.api.bango.refund.post.return_value = self.bango_ret(PENDING)
        solitude.get.return_value = self.refund_tx_ret()
        res = transaction_refund(self.req, self.uuid)
        refund_count = Contribution.objects.all().count()

        # Check no refund Contributions created.
        res = self.client.post(self.url, {'refund_reason': 'text'})
        assert refund_count == Contribution.objects.all().count()
        self.assert3xx(res, reverse('lookup.transaction_summary',
                                    args=[self.uuid]))

    @mock.patch('mkt.lookup.views.client')
    def test_refund_slumber_error(self, solitude):
        for exception in (exceptions.HttpClientError,
                          exceptions.HttpServerError):
            solitude.api.bango.refund.post.side_effect = exception
            res = transaction_refund(self.req, self.uuid)

            # Check no refund Contributions created.
            assert not self.contrib.get_refund_contribs().exists()
            self.assert3xx(res, self.summary_url)

    @mock.patch('mkt.lookup.views.client')
    def test_redirect(self, solitude):
        solitude.api.bango.refund.post.return_value = self.bango_ret(PENDING)
        solitude.get.return_value = self.refund_tx_ret()

        res = self.client.post(self.url, {'refund_reason': 'text'})
        self.assert3xx(res, reverse('lookup.transaction_summary',
                                    args=[self.uuid]))

    @mock.patch('mkt.lookup.views.client')
    def test_403_reg_user(self, solitude):
        solitude.api.bango.refund.post.return_value = self.bango_ret(PENDING)
        solitude.get.return_value = self.refund_tx_ret()

        self.login(self.user)
        res = self.client.post(self.url, {'refund_reason': 'text'})
        eq_(res.status_code, 403)


class TestAppSearch(ESTestCase, SearchTestMixin):
    fixtures = fixture('user_support_staff', 'user_999', 'webapp_337141',
                       'user_operator')

    def setUp(self):
        super(TestAppSearch, self).setUp()
        self.url = reverse('lookup.app_search')
        self.app = Webapp.objects.get(pk=337141)
        self.login('support-staff@mozilla.com')

    def search(self, *args, **kwargs):
        if 'lang' not in kwargs:
            kwargs.update({'lang': 'en-US'})
        return super(TestAppSearch, self).search(*args, **kwargs)

    def verify_result(self, data):
        eq_(data['objects'][0]['name'], self.app.name.localized_string)
        eq_(data['objects'][0]['id'], self.app.pk)
        eq_(data['objects'][0]['url'], reverse('lookup.app_summary',
                                               args=[self.app.pk]))
        eq_(data['objects'][0]['app_slug'], self.app.app_slug)
        eq_(data['objects'][0]['status'],
            mkt.STATUS_CHOICES_API_v2[self.app.status])

    def test_auth_required(self):
        self.client.logout()
        res = self.client.get(self.url)
        eq_(res.status_code, 403)

    def test_operator(self):
        self.login('operator@mozilla.com')
        res = self.client.get(self.url, {'q': self.app.pk})
        eq_(res.status_code, 200)

    def test_by_name_part(self):
        self.app.name = 'This is Steamcube'
        self.app.save()
        self.refresh('webapp')
        data = self.search(q='steamcube')
        self.verify_result(data)

    def test_by_name_unreviewed(self):
        # Just the same as the above test, but with an unreviewed app.
        self.app.status = mkt.STATUS_PENDING
        self.test_by_name_part()

    def test_by_deleted_app(self):
        self.app.delete()
        self.refresh('webapp')
        data = self.search(q='something')
        self.verify_result(data)

    def test_multiword(self):
        self.app.name = 'Firefox Marketplace'
        self.app.save()
        self.refresh('webapp')
        data = self.search(q='Firefox Marketplace')
        self.verify_result(data)

    def test_by_stem_name(self):
        self.app.name = 'Instigated'
        self.app.save()
        self.refresh('webapp')
        data = self.search(q='instigate')
        self.verify_result(data)

    def test_by_guid(self):
        self.app.update(guid='1ab2c3d4-1234-5678-ab12-c34defa5b678')
        self.refresh('webapp')
        data = self.search(q=self.app.guid)
        self.verify_result(data)

    def test_by_id(self):
        data = self.search(q=self.app.pk)
        self.verify_result(data)

    @mock.patch('mkt.lookup.views.AppLookupSearchView.paginate_by', 2)
    @mock.patch('mkt.lookup.views.AppLookupSearchView.max_paginate_by', 3)
    def test_all_results(self):
        for x in range(4):
            app_factory(name='chr' + str(x))
        self.refresh('webapp')

        # Test search limit.
        data = self.search(q='chr')
        eq_(len(data['objects']), 2)

        # Test maximum search result.
        data = self.search(q='chr', limit='max')
        eq_(len(data['objects']), 3)

    def test_statuses(self):
        for status, api_status in mkt.STATUS_CHOICES_API_v2.items():
            if status == mkt.STATUS_DELETED:
                # Deleted status is too special to recover from, so it needs
                # its own test.
                continue
            self.app.update(status=status)
            self.refresh('webapp')
            data = self.search(q='something')
            eq_(data['objects'][0]['status'], api_status)

    def test_deleted(self):
        self.app.update(status=mkt.STATUS_DELETED)
        self.refresh('webapp')
        data = self.search(q='something')
        eq_(data['objects'][0]['status'], 'deleted')

    def test_disabled(self):
        """We override the status for disabled apps to be 'disabled'."""
        self.app.update(disabled_by_user=True)
        self.refresh('webapp')
        data = self.search(q=self.app.app_slug)
        eq_(data['objects'][0]['status'], 'disabled')


class AppSummaryTest(SummaryTest):
    fixtures = fixture('prices', 'webapp_337141', 'user_support_staff')

    def _setUp(self):
        self.app = Webapp.objects.get(pk=337141)
        self.url = reverse('lookup.app_summary',
                           args=[self.app.pk])
        self.user = UserProfile.objects.get(email='steamcube@mozilla.com')
        self.login('support-staff@mozilla.com')

    def summary(self, expected_status=200):
        res = self.client.get(self.url)
        eq_(res.status_code, expected_status)
        return res


@mock.patch('mkt.webapps.models.Webapp.get_cached_manifest', mock.Mock)
class TestAppSummary(AppSummaryTest):
    fixtures = fixture('prices', 'user_admin', 'user_support_staff',
                       'webapp_337141', 'user_operator')

    def setUp(self):
        super(TestAppSummary, self).setUp()
        self._setUp()

    def test_slug(self):
        self.url = reverse('lookup.app_summary', args=[self.app.app_slug])
        self.summary()

    def test_app_deleted(self):
        self.app.delete()
        self.summary()

    def test_packaged_app_deleted(self):
        self.app.update(is_packaged=True)
        ver = version_factory(addon=self.app)
        file_factory(version=ver)
        self.app.delete()
        self.summary()

    def test_authors(self):
        user = UserProfile.objects.get(email='steamcube@mozilla.com')
        res = self.summary()
        eq_(res.context['authors'][0].display_name, user.display_name)

    def test_status(self):
        res = self.summary()
        assert 'Published' in pq(res.content)('.column-b dd').eq(5).text()

    def test_disabled(self):
        self.app.update(disabled_by_user=True)
        res = self.summary()
        text = pq(res.content)('.column-b dd').eq(5).text()
        assert 'Published' not in text
        assert 'disabled by user' in text

    def test_tarako_enabled(self):
        tag = Tag(tag_text='tarako')
        tag.save_tag(self.app)
        res = self.summary()
        text = 'Tarako enabled'
        assert text in pq(res.content)('.column-b dd').eq(6).text()

    def test_tarako_disabled_not_pending(self):
        res = self.summary()
        texta = 'Tarako not enabled |'
        textb = 'Review not requested'
        assert texta in pq(res.content)('.column-b dd').eq(6).text()
        assert textb in pq(res.content)('.column-b dd').eq(6).text()

    def test_tarako_review_pending(self):
        self.app.additionalreview_set.create(queue=QUEUE_TARAKO)
        res = self.summary()
        texta = 'Tarako not enabled |'
        textb = 'Review pending'
        assert texta in pq(res.content)('.column-b dd').eq(6).text()
        assert textb in pq(res.content)('.column-b dd').eq(6).text()

    def test_visible_authors(self):
        AddonUser.objects.all().delete()
        for role in (mkt.AUTHOR_ROLE_DEV,
                     mkt.AUTHOR_ROLE_OWNER,
                     mkt.AUTHOR_ROLE_VIEWER,
                     mkt.AUTHOR_ROLE_SUPPORT):
            role_name = unicode(mkt.AUTHOR_CHOICES_NAMES[role])
            user = user_factory(display_name=role_name)
            role = AddonUser.objects.create(user=user,
                                            addon=self.app,
                                            role=role)
            self.app.addonuser_set.add(role)
        res = self.summary()

        eq_(sorted([u.display_name for u in res.context['authors']]),
            [unicode(mkt.AUTHOR_CHOICES_NAMES[mkt.AUTHOR_ROLE_DEV]),
             unicode(mkt.AUTHOR_CHOICES_NAMES[mkt.AUTHOR_ROLE_OWNER])])

    def test_details(self):
        res = self.summary()
        eq_(res.context['app'].manifest_url, self.app.manifest_url)
        eq_(res.context['app'].premium_type, mkt.ADDON_FREE)
        eq_(res.context['price'], None)

    def test_price(self):
        self.make_premium(self.app)
        res = self.summary()
        eq_(res.context['price'], self.app.premium.price)

    def test_abuse_reports(self):
        for i in range(2):
            AbuseReport.objects.create(addon=self.app,
                                       ip_address='10.0.0.1',
                                       message='spam and porn everywhere')
        res = self.summary()
        eq_(res.context['abuse_reports'], 2)

    def test_permissions(self):
        manifest = json.dumps({
            'permissions': {
                'geolocation': {
                    'description': 'Required to know where you are.'
                }
            }
        })
        self.app.latest_version.manifest_json.update(manifest=manifest)

        res = self.summary()
        eq_(res.context['permissions'], json.loads(manifest)['permissions'])

    def test_version_history_non_packaged(self):
        res = self.summary()
        eq_(pq(res.content)('section.version-history').length, 0)

    def test_version_history_packaged(self):
        self.app.update(is_packaged=True)
        self.version = self.app.current_version
        self.file = self.version.all_files[0]
        self.file.update(filename='mozball.zip')

        res = self.summary()
        eq_(pq(res.content)('section.version-history').length, 1)
        assert 'mozball.zip' in pq(res.content)(
            'section.version-history a.download').attr('href')

    def test_edit_link_staff(self):
        res = self.summary()
        eq_(pq(res.content)('.shortcuts li').length, 4)
        eq_(pq(res.content)('.shortcuts li').eq(3).text(), 'Edit Listing')

    def test_operator_200(self):
        self.login('operator@mozilla.com')
        res = self.client.get(self.url)
        eq_(res.status_code, 200)

    def test_priority_button_available(self):
        res = self.summary()
        eq_(pq(res.content)('section.column-b button.button').attr('name'),
            'prioritize')
        eq_(pq(res.content)('section.column-b button.button').text(),
            'Prioritize Review?')

    def test_priority_button_already_prioritized(self):
        self.app.update(priority_review=True)
        res = self.summary()
        eq_(pq(res.content)('section.column-b button.button,disabled')
            .attr('name'), 'prioritize')
        eq_(pq(res.content)('section.column-b button.button,disabled').text(),
            'Review Prioritized')

    def test_priority_button_works(self):
        staff = UserProfile.objects.get(email='support-staff@mozilla.com')
        req = req_factory_factory(self.url, post=True, user=staff,
                                  data={'prioritize': 'true'})
        app_summary(req, self.app.id)
        self.app.reload()
        eq_(self.app.priority_review, True)

    @mock.patch.object(settings, 'PAYMENT_PROVIDERS', ['bango', 'reference'])
    def test_multiple_payment_accounts(self):
        self.add_payment_accounts([PROVIDER_BANGO, PROVIDER_REFERENCE])
        res = self.summary()
        self.verify_bango_portal(self.app, res)


class TestAppSummaryPurchases(AppSummaryTest):

    def setUp(self):
        super(TestAppSummaryPurchases, self).setUp()
        self._setUp()

    def assert_totals(self, data):
        eq_(data['total'], 6)
        six_bucks = numbers.format_currency(6, 'USD',
                                            locale=numbers.LC_NUMERIC)
        three_euro = numbers.format_currency(3, 'EUR',
                                             locale=numbers.LC_NUMERIC)
        eq_(set(data['amounts']), set([six_bucks, three_euro]))
        eq_(len(data['amounts']), 2)

    def assert_empty(self, data):
        eq_(data['total'], 0)
        eq_(sorted(data['amounts']), [])

    def purchase(self, created=None, typ=mkt.CONTRIB_PURCHASE):
        for curr, amount in (('USD', '2.00'), ('EUR', '1.00')):
            for i in range(3):
                c = Contribution.objects.create(addon=self.app,
                                                user=self.user,
                                                amount=Decimal(amount),
                                                currency=curr,
                                                type=typ)
                if created:
                    c.update(created=created)

    def test_24_hr(self):
        self.purchase()
        res = self.summary()
        self.assert_totals(res.context['purchases']['last_24_hours'])

    def test_ignore_older_than_24_hr(self):
        self.purchase(created=datetime.now() - timedelta(days=1,
                                                         minutes=1))
        res = self.summary()
        self.assert_empty(res.context['purchases']['last_24_hours'])

    def test_7_days(self):
        self.purchase(created=datetime.now() - timedelta(days=6,
                                                         minutes=55))
        res = self.summary()
        self.assert_totals(res.context['purchases']['last_7_days'])

    def test_ignore_older_than_7_days(self):
        self.purchase(created=datetime.now() - timedelta(days=7,
                                                         minutes=1))
        res = self.summary()
        self.assert_empty(res.context['purchases']['last_7_days'])

    def test_alltime(self):
        self.purchase(created=datetime.now() - timedelta(days=31))
        res = self.summary()
        self.assert_totals(res.context['purchases']['alltime'])

    def test_ignore_non_purchases(self):
        for typ in [mkt.CONTRIB_REFUND,
                    mkt.CONTRIB_CHARGEBACK,
                    mkt.CONTRIB_PENDING]:
            self.purchase(typ=typ)
        res = self.summary()
        self.assert_empty(res.context['purchases']['alltime'])


class TestAppSummaryRefunds(AppSummaryTest):
    fixtures = AppSummaryTest.fixtures + fixture('user_999', 'user_admin')

    def setUp(self):
        super(TestAppSummaryRefunds, self).setUp()
        self._setUp()
        self.user = UserProfile.objects.get(email='regular@mozilla.com')
        self.contrib1 = self.purchase()
        self.contrib2 = self.purchase()
        self.contrib3 = self.purchase()
        self.contrib4 = self.purchase()

    def purchase(self):
        return Contribution.objects.create(addon=self.app,
                                           user=self.user,
                                           amount=Decimal('0.99'),
                                           currency='USD',
                                           paykey='AP-1235',
                                           type=mkt.CONTRIB_PURCHASE)

    def refund(self, refunds):
        for contrib, status in refunds:
            Refund.objects.create(contribution=contrib,
                                  status=status,
                                  user=self.user)

    def test_requested(self):
        self.refund(((self.contrib1, mkt.REFUND_APPROVED),
                     (self.contrib2, mkt.REFUND_APPROVED),
                     (self.contrib3, mkt.REFUND_DECLINED),
                     (self.contrib4, mkt.REFUND_DECLINED)))
        res = self.summary()
        eq_(res.context['refunds']['requested'], 2)
        eq_(res.context['refunds']['percent_of_purchases'], '50.0%')

    def test_no_refunds(self):
        res = self.summary()
        eq_(res.context['refunds']['requested'], 0)
        eq_(res.context['refunds']['percent_of_purchases'], '0.0%')
        eq_(res.context['refunds']['auto-approved'], 0)
        eq_(res.context['refunds']['approved'], 0)
        eq_(res.context['refunds']['rejected'], 0)

    def test_auto_approved(self):
        self.refund(((self.contrib1, mkt.REFUND_APPROVED),
                     (self.contrib2, mkt.REFUND_APPROVED_INSTANT)))
        res = self.summary()
        eq_(res.context['refunds']['auto-approved'], 1)

    def test_approved(self):
        self.refund(((self.contrib1, mkt.REFUND_APPROVED),
                     (self.contrib2, mkt.REFUND_DECLINED)))
        res = self.summary()
        eq_(res.context['refunds']['approved'], 1)

    def test_rejected(self):
        self.refund(((self.contrib1, mkt.REFUND_APPROVED),
                     (self.contrib2, mkt.REFUND_DECLINED),
                     (self.contrib3, mkt.REFUND_FAILED)))
        res = self.summary()
        eq_(res.context['refunds']['rejected'], 2)


class TestPurchases(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141', 'users')

    def setUp(self):
        self.app = Webapp.objects.get(pk=337141)
        self.reviewer = UserProfile.objects.get(email='admin@mozilla.com')
        self.user = UserProfile.objects.get(email='regular@mozilla.com')
        self.url = reverse('lookup.user_purchases', args=[self.user.pk])

    def test_not_allowed(self):
        self.client.logout()
        self.assertLoginRequired(self.client.get(self.url))

    def test_not_even_mine(self):
        self.login(self.user)
        eq_(self.client.get(self.url).status_code, 403)

    def test_access(self):
        self.login(self.reviewer)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        eq_(pq(res.content)('p.notice').length, 1)

    def test_purchase_shows_up(self):
        Contribution.objects.create(user=self.user, addon=self.app,
                                    amount=1, type=mkt.CONTRIB_PURCHASE)
        self.login(self.reviewer)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        doc = pq(res.content)
        eq_(doc('div.product-lookup-list a').attr('href'),
            self.app.get_detail_url())

    def test_no_support_link(self):
        for type_ in [mkt.CONTRIB_PURCHASE]:
            Contribution.objects.create(user=self.user, addon=self.app,
                                        amount=1, type=type_)
        self.login(self.reviewer)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        doc = pq(res.content)
        eq_(len(doc('.item a.request-support')), 0)


class TestActivity(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141', 'users')

    def setUp(self):
        self.app = Webapp.objects.get(pk=337141)
        self.reviewer = UserProfile.objects.get(email='admin@mozilla.com')
        self.user = UserProfile.objects.get(email='regular@mozilla.com')
        self.url = reverse('lookup.user_activity', args=[self.user.pk])

    def test_not_allowed(self):
        self.client.logout()
        self.assertLoginRequired(self.client.get(self.url))

    def test_not_even_mine(self):
        self.login(self.user)
        eq_(self.client.get(self.url).status_code, 403)

    def test_access(self):
        self.login(self.reviewer)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        eq_(len(pq(res.content)('.simple-log div')), 0)

    def test_log(self):
        self.login(self.reviewer)
        self.client.get(self.url)
        log_item = ActivityLog.objects.get(action=mkt.LOG.ADMIN_VIEWED_LOG.id)
        eq_(len(log_item.arguments), 1)
        eq_(log_item.arguments[0].id, self.reviewer.id)
        eq_(log_item.user, self.user)

    def test_display(self):
        mkt.log(mkt.LOG.PURCHASE_ADDON, self.app, user=self.user)
        mkt.log(mkt.LOG.ADMIN_USER_EDITED, self.user, 'spite', user=self.user)
        self.login(self.reviewer)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        doc = pq(res.content)
        assert 'purchased' in doc('li.item').eq(0).text()
        assert 'edited' in doc('li.item').eq(1).text()


class TestAppActivity(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141', 'users')

    def setUp(self):
        self.app = Webapp.objects.get(pk=337141)
        self.reviewer = UserProfile.objects.get(email='admin@mozilla.com')
        self.user = UserProfile.objects.get(email='regular@mozilla.com')
        self.url = reverse('lookup.app_activity', args=[self.app.pk])

    def test_not_allowed(self):
        self.client.logout()
        self.assertLoginRequired(self.client.get(self.url))

    def test_not_even_mine(self):
        self.login(self.user)
        eq_(self.client.get(self.url).status_code, 403)

    def test_access(self):
        self.login(self.reviewer)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)

    def test_logs(self):
        # Admin log.
        mkt.log(mkt.LOG.COMMENT_VERSION, self.app, self.app.current_version,
                user=self.user)
        # Regular log.
        mkt.log(mkt.LOG.MANIFEST_UPDATED, self.app, user=self.user)

        self.login(self.reviewer)
        res = self.client.get(self.url)
        doc = pq(res.content)
        assert 'manifest updated' in doc('li.item').eq(0).text()
        assert 'Comment on' in doc('li.item').eq(1).text()


class TestWebsiteSearch(ESTestCase, SearchTestMixin):
    fixtures = fixture('user_support_staff', 'user_999')

    def setUp(self):
        super(TestWebsiteSearch, self).setUp()
        self.url = reverse('lookup.website_search')
        self.website = website_factory()
        self.refresh('website')
        self.login('support-staff@mozilla.com')

    def search(self, *args, **kwargs):
        if 'lang' not in kwargs:
            kwargs.update({'lang': 'en-US'})
        return super(TestWebsiteSearch, self).search(*args, **kwargs)

    def verify_result(self, data):
        eq_(data['objects'][0]['id'], self.website.pk)
        eq_(data['objects'][0]['name'], self.website.name.localized_string)
        eq_(data['objects'][0]['url'], reverse('lookup.website_summary',
                                               args=[self.website.pk]))

    def test_auth_required(self):
        self.client.logout()
        res = self.client.get(self.url)
        eq_(res.status_code, 403)

    def test_by_name(self):
        data = self.search(q=self.website.name.localized_string)
        self.verify_result(data)

    def test_by_id(self):
        data = self.search(q=self.website.pk)
        self.verify_result(data)


class TestWebsiteEdit(mkt.site.tests.TestCase):
    fixtures = fixture('user_support_staff')

    def setUp(self):
        super(TestWebsiteEdit, self).setUp()
        self.website = website_factory()
        self.url = reverse('lookup.website_edit', args=[self.website.pk])
        self.login('support-staff@mozilla.com')

    def test_auth(self):
        eq_(self.client.get(self.url).status_code, 200)
        eq_(self.client.post(self.url, {'keywords': 'blah'}).status_code, 200)

        self.client.logout()
        login_url = '%s?to=%s' % (reverse('users.login'), urlquote(self.url))
        self.assert3xx(self.client.get(self.url), login_url)
        self.assert3xx(self.client.post(self.url), login_url)

    def test_basic(self):
        data = {
            'name_en-us': 'New name',
            'description_en-us': 'New description',
            'url': 'http://example.com/',
            'status': 4,
            'categories': ['kids', 'games'],
            'devices': [DEVICE_GAIA.id],
        }
        resp = self.client.post(self.url, data)
        self.assert3xx(resp, reverse('lookup.website_summary',
                                     args=[self.website.pk]))
        self.website.reload()
        eq_(unicode(self.website.name), data['name_en-us'])
        eq_(unicode(self.website.description), data['description_en-us'])
        eq_(self.website.url, data['url'])


class TestGroupSearch(TestCase, SearchTestMixin):
    fixtures = fixture('user_support_staff', 'user_operator', 'group_admin')

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse('lookup.group_search')

    def setUp(self):
        super(TestGroupSearch, self).setUp()
        self.group = Group.objects.get(name='Operators')
        self.login(UserProfile.objects.get(email='support-staff@mozilla.com'))

    def verify_result(self, data):
        eq_(data['objects'][0]['name'], self.group.name)
        eq_(data['objects'][0]['rules'], self.group.rules)
        eq_(data['objects'][0]['id'], self.group.pk)
        eq_(data['objects'][0]['url'], reverse('lookup.group_summary',
                                               args=[self.group.pk]))

    def test_by_name(self):
        self.group.update(name='Red Leicester')
        data = self.search(q='leices')
        self.verify_result(data)

    def test_by_id(self):
        data = self.search(q=self.group.pk)
        self.verify_result(data)

    def test_by_rules(self):
        self.group.update(rules='holes:many')
        data = self.search(q='many')
        self.verify_result(data)

    @mock.patch('mkt.constants.lookup.SEARCH_LIMIT', 2)
    @mock.patch('mkt.constants.lookup.MAX_RESULTS', 3)
    def test_all_results(self):
        for x in range(4):
            name = 'chr' + str(x)
            Group.objects.create(name=name, rules="%s:%s" % (x, x))

        # Test not at search limit.
        data = self.search(q='operators')
        eq_(len(data['objects']), 1)

        # Test search limit.
        data = self.search(q='chr')
        eq_(len(data['objects']), 2)

        # Test maximum search result.
        data = self.search(q='chr', limit='max')
        eq_(len(data['objects']), 3)


class TestGroupSummary(TestCase):
    fixtures = fixture('user_support_staff', 'user_operator')

    @classmethod
    def setUpTestData(cls):
        cls.group = Group.objects.get(name='Operators')
        cls.reg_user = user_factory(email='regular@mozilla.com')
        cls.opr_user = UserProfile.objects.get(email='operator@mozilla.com')
        cls.summary_url = reverse('lookup.group_summary', args=[cls.group.pk])

    def setUp(self):
        super(TestGroupSummary, self).setUp()
        self.login(UserProfile.objects.get(email='support-staff@mozilla.com'))

    def test_group_details(self):
        self.group.update(name='Unique-Group-Name', rules='Thing:Do',
                          notes='Much blah blah')
        res = self.client.get(self.summary_url)
        eq_(res.status_code, 200)
        text = pq(res.content)('#prose').eq(0).text()
        ok_(self.group.name in text)
        ok_(self.group.rules in text)
        ok_(self.group.notes in text)

    def test_group_members(self):
        GroupUser.objects.create(
            group=Group.objects.get(name='Operators'), user=self.reg_user)
        res = self.client.get(self.summary_url)
        eq_(res.status_code, 200)
        doc = pq(res.content)
        # Test both users (operator@ and regular@) are there
        eq_(doc('dl.group-memberships dd a').eq(0).text(), self.opr_user.name)
        eq_(doc('dl.group-memberships dd a').eq(1).text(), self.reg_user.name)
