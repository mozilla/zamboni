# -*- coding: utf-8 -*-
import json

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse

import mock
from mock import ANY
from nose.tools import eq_, ok_
from pyquery import PyQuery as pq
from slumber.exceptions import HttpClientError
from waffle.models import Switch

import mkt
import mkt.site.tests
from mkt.constants.payments import (ACCESS_PURCHASE, ACCESS_SIMULATE,
                                    PAYMENT_METHOD_ALL, PAYMENT_METHOD_CARD,
                                    PAYMENT_METHOD_OPERATOR, PROVIDER_BANGO,
                                    PROVIDER_REFERENCE)
from mkt.constants.regions import ALL_REGION_IDS, ESP, GBR, USA
from mkt.developers.models import (AddonPaymentAccount, PaymentAccount,
                                   SolitudeSeller, UserInappKey)
from mkt.developers.tests.test_providers import Patcher
from mkt.developers.views_payments import (get_inapp_config,
                                           require_in_app_payments)
from mkt.prices.models import Price
from mkt.site.fixtures import fixture
from mkt.site.utils import app_factory
from mkt.users.models import UserProfile
from mkt.webapps.models import AddonExcludedRegion as AER
from mkt.webapps.models import (AddonDeviceType, AddonPremium, AddonUpsell,
                                AddonUser, Webapp)


# Id without any significance but to be different of 1.
TEST_PACKAGE_ID = '2'


def setup_payment_account(app, user, uid='uid', package_id=TEST_PACKAGE_ID):
    seller = SolitudeSeller.objects.create(user=user, uuid=uid)
    payment = PaymentAccount.objects.create(
        user=user, solitude_seller=seller, agreed_tos=True, seller_uri=uid,
        uri=uid, account_id=package_id)
    return AddonPaymentAccount.objects.create(
        addon=app, product_uri='/path/to/%s/' % app.pk,
        account_uri=payment.uri, payment_account=payment)


class InappTest(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141', 'user_999')

    def setUp(self):
        self.public_id = 'app-public-id'
        self.pay_key_secret = 'hex-secret-for-in-app-payments'
        self.generic_product_id = '1'
        self.app = Webapp.objects.get(pk=337141)
        self.app.update(premium_type=mkt.ADDON_FREE_INAPP,
                        solitude_public_id=self.public_id)
        self.user = UserProfile.objects.get(pk=31337)
        self.other = UserProfile.objects.get(pk=999)
        self.login(self.user)
        self.account = setup_payment_account(self.app, self.user)
        self.url = reverse('mkt.developers.apps.in_app_config',
                           args=[self.app.app_slug])
        p = mock.patch('mkt.developers.views_payments.client.api')
        self.api = p.start()
        self.addCleanup(p.stop)

    def set_mocks(self):
        """
        Set up mocks to allow in-app payment configuration.
        """
        product = {
            'resource_pk': self.generic_product_id,
            'secret': self.pay_key_secret
        }
        self.api.generic.product.get_object.return_value = product
        self.api.generic.product.get_object_or_404.return_value = product


class TestInappConfig(InappTest):

    def test_key_generation(self):
        self.set_mocks()
        self.client.post(self.url, {})
        self.api.generic.product.assert_called_with(self.generic_product_id)
        args = self.api.generic.product().patch.call_args
        assert 'secret' in args[1]['data']

    def test_when_logged_out(self):
        self.client.logout()
        self.assertLoginRequired(self.client.get(self.url))

    def test_non_team_member_cannot_get_config(self):
        self.login(self.other)
        eq_(self.client.get(self.url).status_code, 403)

    def test_other_developer_can_get_config(self):
        self.login(self.other)
        AddonUser.objects.create(addon=self.app, user=self.other,
                                 role=mkt.AUTHOR_ROLE_DEV)
        # Developer can read, but not reset.
        eq_(self.client.get(self.url).status_code, 200)
        eq_(self.client.post(self.url).status_code, 403)

    def test_not_inapp(self):
        self.app.update(premium_type=mkt.ADDON_PREMIUM)
        eq_(self.client.get(self.url).status_code, 302)

    def test_no_pay_account(self):
        self.app.app_payment_accounts.all().delete()
        eq_(self.client.get(self.url).status_code, 302)


@require_in_app_payments
def render_in_app_view(request, addon_id, addon, *args, **kwargs):
    return 'The view was rendered'


class TestRequireInAppPayments(mkt.site.tests.TestCase):

    def good_app(self):
        addon = mock.Mock(premium_type=mkt.ADDON_INAPPS[0], app_slug='foo')
        addon.has_payment_account.return_value = True
        return addon

    def test_inapp(self):
        response = render_in_app_view(addon=self.good_app(), request=None,
                                      addon_id=None)
        eq_(response, 'The view was rendered')

    @mock.patch('django.contrib.messages.error')
    def test_not_inapp(self, error):
        addon = self.good_app()
        addon.premium_type = mkt.ADDON_FREE
        response = render_in_app_view(addon=addon, request=None, addon_id=None)
        eq_(response.status_code, 302)

    @mock.patch('django.contrib.messages.error')
    def test_no_pay_account(self, error):
        addon = self.good_app()
        addon.has_payment_account.return_value = False
        response = render_in_app_view(addon=addon, request=None, addon_id=None)
        eq_(response.status_code, 302)


class TestInAppPaymentsView(InappTest):

    def setUp(self):
        super(TestInAppPaymentsView, self).setUp()
        self.url = reverse('mkt.developers.apps.in_app_payments',
                           args=[self.app.app_slug])

        self.waffle = self.create_switch('in-app-products')

    def get(self):
        return self.client.get(self.url)

    def test_ok(self):
        res = self.get()
        eq_(res.status_code, 200)

    def test_requires_author(self):
        self.login(self.other)
        eq_(self.get().status_code, 403)

    def test_inapp_products_enabled(self):
        doc = pq(self.get().content)
        ok_(doc('section.primary div#in-app-keys'))
        ok_(doc('section.primary div#in-app-products'))

    def test_inapp_products_disabled(self):
        self.waffle.active = False
        self.waffle.save()
        doc = pq(self.get().content)
        ok_(doc('section.primary div#in-app-keys'))
        ok_(not doc('section.primary div#in-app-products'))


class TestGetInappConfig(InappTest):

    def setUp(self):
        super(TestGetInappConfig, self).setUp()
        self.api.generic.product.get_object.return_value = {
            'secret': self.pay_key_secret,
            'public_id': self.public_id,
        }

    def test_ok(self):
        conf = get_inapp_config(self.app)
        eq_(conf['public_id'], self.app.solitude_public_id)

    def test_not_configured(self):
        self.app.update(solitude_public_id=None)
        with self.assertRaises(ValueError):
            get_inapp_config(self.app)


class TestInAppProductsView(InappTest):

    def setUp(self):
        super(TestInAppProductsView, self).setUp()
        self.waffle = Switch.objects.create(name='in-app-products',
                                            active=True)
        self.url = reverse('mkt.developers.apps.in_app_products',
                           args=[self.app.app_slug])

    def get(self):
        return self.client.get(self.url)

    def test_finds_products(self):
        eq_(self.get().status_code, 200)

    def test_requires_author(self):
        self.login(self.other)
        eq_(self.get().status_code, 403)

    def test_without_waffle(self):
        self.waffle.active = False
        self.waffle.save()
        eq_(self.get().status_code, 404)

    def test_origin(self):
        self.app.update(is_packaged=True, app_domain='http://f.c')
        doc = pq(self.get().content)
        ok_(doc('section.primary div#buglink-notification'))
        div = doc('#in-app-products')

        url = div.attr('data-list-url')
        assert url.endswith('http:%2F%2Ff.c/in-app/'), (
            'Unexpected URL: {u}'.format(u=url))

        url = div.attr('data-detail-url-format')
        assert url.endswith('http:%2F%2Ff.c/in-app/%7Bguid%7D/'), (
            'Unexpected URL: {u}'.format(u=url))

    def test_no_declared_origin(self):
        self.app.update(is_packaged=True, app_domain=None)
        doc = pq(self.get().content)
        div = doc('#in-app-products')
        mkt_origin = 'marketplace:{}'.format(self.app.guid)
        url = div.attr('data-list-url')
        assert url.endswith('{}/in-app/'.format(mkt_origin)), (
            'Unexpected URL: {u}'.format(u=url))

        url = div.attr('data-detail-url-format')
        assert url.endswith('{}/in-app/%7Bguid%7D/'.format(mkt_origin)), (
            'Unexpected URL: {u}'.format(u=url))

    def test_hosted(self):
        self.app.update(is_packaged=False, app_domain='http://f.c')
        doc = pq(self.get().content)
        ok_(not doc('section.primary div#origin-notification'))
        ok_(doc('section.primary div#buglink-notification'))


class TestInappSecret(InappTest):

    def setUp(self):
        super(TestInappSecret, self).setUp()
        self.url = reverse('mkt.developers.apps.in_app_secret',
                           args=[self.app.app_slug])

    def test_show_secret(self):
        self.set_mocks()
        resp = self.client.get(self.url)
        eq_(resp.content, self.pay_key_secret)
        self.api.generic.product.get_object.assert_called_with(
            public_id=self.public_id)

    def test_when_logged_out(self):
        self.client.logout()
        self.assertLoginRequired(self.client.get(self.url))

    def test_non_team_member_cannot_get_secret(self):
        self.login('regular@mozilla.com')
        eq_(self.client.get(self.url).status_code, 403)

    def test_other_developers_can_access_secret(self):
        self.set_mocks()
        self.login(self.other)
        AddonUser.objects.create(addon=self.app, user=self.other,
                                 role=mkt.AUTHOR_ROLE_DEV)
        resp = self.client.get(self.url)
        eq_(resp.content, self.pay_key_secret)


class InappKeysTest(InappTest):

    def setUp(self):
        super(InappKeysTest, self).setUp()
        self.url = reverse('mkt.developers.apps.in_app_keys')
        self.seller_uri = '/seller/1/'
        self.product_pk = 2

    def setup_solitude(self):
        self.api.generic.seller.post.return_value = {
            'resource_uri': self.seller_uri}
        self.api.generic.product.post.return_value = {
            'resource_pk': self.product_pk}


class TestInappKeys(InappKeysTest):

    def test_logged_out(self):
        self.client.logout()
        self.assertLoginRequired(self.client.get(self.url))

    def test_no_key(self):
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        eq_(res.context['key'], None)

    def test_key_generation(self):
        self.setup_solitude()
        res = self.client.post(self.url)

        ok_(res['Location'].endswith(self.url), res)
        ok_(self.api.generic.seller.post.called)
        ok_(self.api.generic.product.post.called)
        key = UserInappKey.objects.get()
        eq_(key.solitude_seller.resource_uri, self.seller_uri)
        eq_(key.seller_product_pk, self.product_pk)
        m = self.api.generic.product.post.mock_calls
        eq_(m[0][2]['data']['access'], ACCESS_SIMULATE)

    @mock.patch('mkt.developers.models.UserInappKey.public_id')
    def test_reset(self, mock_public_id):
        self.setup_solitude()
        key = UserInappKey.create(self.user)
        product = mock.Mock()
        self.api.generic.product.return_value = product

        self.client.post(self.url)
        product.patch.assert_called_with(data={'secret': ANY})
        self.api.generic.product.assert_called_with(key.seller_product_pk)

    def test_keys_page_renders_when_solitude_raises_404(self):
        UserInappKey.create(self.user)
        self.api.generic.product.side_effect = HttpClientError()

        res = self.client.get(self.url)
        eq_(res.status_code, 200)

        # Test that a message is sent to the user
        eq_(len(res.context['messages']), 1)


class TestInappKeySecret(InappKeysTest):

    def setup_objects(self):
        self.setup_solitude()
        key = UserInappKey.create(self.user)
        self.url = reverse('mkt.developers.apps.in_app_key_secret',
                           args=[key.pk])

    def test_logged_out(self):
        self.setup_objects()
        self.client.logout()
        self.assertLoginRequired(self.client.get(self.url))

    def test_different(self):
        self.setup_objects()
        self.login(self.other)
        eq_(self.client.get(self.url).status_code, 403)

    def test_secret(self):
        self.setup_objects()
        secret = 'not telling'
        product = mock.Mock()
        product.get.return_value = {'secret': secret}
        self.api.generic.product.return_value = product

        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        eq_(res.content, secret)


class TestPayments(Patcher, mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141', 'user_999', 'group_admin',
                       'user_admin', 'user_admin_group', 'prices')

    def setUp(self):
        super(TestPayments, self).setUp()
        self.webapp = self.get_webapp()
        AddonDeviceType.objects.create(
            addon=self.webapp, device_type=mkt.DEVICE_GAIA.id)
        self.url = self.webapp.get_dev_url('payments')

        self.user = UserProfile.objects.get(pk=31337)
        self.other = UserProfile.objects.get(pk=999)
        self.admin = UserProfile.objects.get(email='admin@mozilla.com')

        # Default to logging in as the app owner.
        self.login(self.user)
        self.price = Price.objects.filter()[0]

    def get_webapp(self):
        return Webapp.objects.get(pk=337141)

    def get_region_list(self):
        return list(AER.objects.values_list('region', flat=True))

    def get_postdata(self, extension):
        base = {'regions': self.get_region_list(),
                'free_platforms': ['free-%s' % dt.class_name for dt in
                                   self.webapp.device_types],
                'paid_platforms': ['paid-%s' % dt.class_name for dt in
                                   self.webapp.device_types]}
        if 'accounts' in extension:
            extension['form-TOTAL_FORMS'] = 1
            extension['form-INITIAL_FORMS'] = 1
            extension['form-MAX_NUM_FORMS'] = 1
            extension['form-0-accounts'] = extension['accounts']
            del extension['accounts']
        base.update(extension)
        return base

    def test_free(self):
        res = self.client.post(
            self.url, self.get_postdata({'toggle-paid': 'free'}), follow=True)
        eq_(self.get_webapp().premium_type, mkt.ADDON_FREE)
        eq_(res.context['is_paid'], False)

    def test_premium_passes(self):
        self.webapp.update(premium_type=mkt.ADDON_FREE)
        res = self.client.post(self.url,
                               self.get_postdata({'toggle-paid': 'paid'}),
                               follow=True)
        eq_(self.get_webapp().premium_type, mkt.ADDON_PREMIUM)
        eq_(res.context['is_paid'], True)

    def test_check_api_url_in_context(self):
        self.webapp.update(premium_type=mkt.ADDON_FREE)
        res = self.client.get(self.url)
        eq_(res.context['api_pricelist_url'], reverse('price-list'))

    def test_regions_display_free(self):
        self.webapp.update(premium_type=mkt.ADDON_FREE)
        res = self.client.get(self.url)
        pqr = pq(res.content)
        eq_(len(pqr('#regions-island')), 1)
        eq_(len(pqr('#paid-regions-island')), 0)

    def test_regions_display_premium(self):
        self.webapp.update(premium_type=mkt.ADDON_PREMIUM)
        res = self.client.get(self.url)
        pqr = pq(res.content)
        eq_(len(pqr('#regions-island')), 0)
        eq_(len(pqr('#paid-regions-island')), 1)

    def test_free_with_in_app_tier_id_in_content(self):
        price_tier_zero = Price.objects.get(price='0.00')
        self.webapp.update(premium_type=mkt.ADDON_PREMIUM)
        res = self.client.get(self.url)
        pqr = pq(res.content)
        eq_(len(pqr('#region-list[data-tier-zero-id]')), 1)
        eq_(int(pqr('#region-list').attr(
            'data-tier-zero-id')), price_tier_zero.pk)

    def test_not_applicable_data_attr_in_content(self):
        self.webapp.update(premium_type=mkt.ADDON_PREMIUM)
        res = self.client.get(self.url)
        pqr = pq(res.content)
        eq_(len(pqr('#region-list[data-not-applicable-msg]')), 1)

    def test_pay_method_ids_in_context(self):
        self.webapp.update(premium_type=mkt.ADDON_PREMIUM)
        res = self.client.get(self.url)
        self.assertSetEqual(res.context['payment_methods'].keys(),
                            [PAYMENT_METHOD_ALL, PAYMENT_METHOD_CARD,
                             PAYMENT_METHOD_OPERATOR])

    def test_free_with_in_app_deletes_upsell(self):
        self.make_premium(self.webapp)
        new_upsell_app = Webapp.objects.create(
            status=self.webapp.status,
            name='upsell-%s' % self.webapp.id,
            premium_type=mkt.ADDON_FREE)
        new_upsell = AddonUpsell(premium=self.webapp)
        new_upsell.free = new_upsell_app
        new_upsell.save()
        assert self.get_webapp().upsold is not None
        self.client.post(self.url,
                         self.get_postdata({'price': 'free',
                                            'allow_inapp': 'True',
                                            'regions': ALL_REGION_IDS}),
                         follow=True)
        eq_(self.get_webapp().upsold, None)
        eq_(AddonPremium.objects.all().count(), 0)

    def test_premium_in_app_passes(self):
        self.webapp.update(premium_type=mkt.ADDON_FREE)
        res = self.client.post(
            self.url, self.get_postdata({'toggle-paid': 'paid'}))
        self.assert3xx(res, self.url)
        res = self.client.post(
            self.url, self.get_postdata({'allow_inapp': True,
                                         'price': self.price.pk,
                                         'regions': ALL_REGION_IDS}))
        self.assert3xx(res, self.url)
        eq_(self.get_webapp().premium_type, mkt.ADDON_PREMIUM_INAPP)

    @mock.patch('mkt.webapps.models.Webapp.is_fully_complete')
    def test_later_then_free(self, complete_mock):
        complete_mock.return_value = True
        self.webapp.update(premium_type=mkt.ADDON_PREMIUM,
                           status=mkt.STATUS_NULL,
                           highest_status=mkt.STATUS_PENDING)
        self.make_premium(self.webapp)
        res = self.client.post(
            self.url, self.get_postdata({'toggle-paid': 'free',
                                         'price': self.price.pk}))
        self.assert3xx(res, self.url)
        eq_(self.get_webapp().status, mkt.STATUS_PENDING)
        eq_(AddonPremium.objects.all().count(), 0)

    def test_premium_price_initial_already_set(self):
        self.make_premium(self.webapp)
        r = self.client.get(self.url)
        eq_(pq(r.content)('select[name=price] option[selected]').attr('value'),
            str(self.webapp.premium.price.id))

    def test_premium_price_initial_use_default(self):
        Price.objects.create(price='10.00')  # Make one more tier.

        self.webapp.update(premium_type=mkt.ADDON_FREE)
        res = self.client.post(
            self.url, self.get_postdata({'toggle-paid': 'paid'}), follow=True)
        pqr = pq(res.content)
        eq_(pqr('select[name=price] option[selected]').attr('value'),
            str(Price.objects.get(price='0.99').id))

    def test_starting_with_free_inapp_has_free_selected(self):
        self.webapp.update(premium_type=mkt.ADDON_FREE_INAPP)
        res = self.client.get(self.url)
        pqr = pq(res.content)
        eq_(pqr('select[name=price] option[selected]').attr('value'), 'free')

    def test_made_free_inapp_has_free_selected(self):
        self.make_premium(self.webapp)
        res = self.client.post(
            self.url, self.get_postdata({'price': 'free',
                                         'allow_inapp': 'True'}), follow=True)
        pqr = pq(res.content)
        eq_(pqr('select[name=price] option[selected]').attr('value'), 'free')

    def test_made_free_inapp_then_free(self):
        self.webapp.update(premium_type=mkt.ADDON_PREMIUM)
        self.make_premium(self.webapp)
        self.client.post(
            self.url, self.get_postdata({'price': 'free',
                                         'allow_inapp': 'True',
                                         'regions': ALL_REGION_IDS}))
        eq_(self.get_webapp().premium_type, mkt.ADDON_FREE_INAPP)
        self.client.post(
            self.url, self.get_postdata({'toggle-paid': 'free',
                                         'regions': ALL_REGION_IDS}))
        eq_(self.get_webapp().premium_type, mkt.ADDON_FREE)

    def test_free_with_inapp_without_account_has_incomplete_status(self):
        self.webapp.update(premium_type=mkt.ADDON_FREE)
        # Toggle to paid
        self.client.post(
            self.url, self.get_postdata({'toggle-paid': 'paid'}))
        res = self.client.post(
            self.url, self.get_postdata({'price': 'free',
                                         'allow_inapp': 'True',
                                         'regions': ALL_REGION_IDS}))
        self.assert3xx(res, self.url)
        eq_(self.get_webapp().status, mkt.STATUS_NULL)
        eq_(AddonPremium.objects.all().count(), 0)
        res = self.client.get(self.url)
        pqr = pq(res.content)
        eq_(len(pqr('#paid-island-incomplete:not(.hidden)')), 1)

    def test_paid_app_without_account_has_incomplete_status(self):
        self.webapp.update(premium_type=mkt.ADDON_FREE)
        # Toggle to paid
        self.client.post(
            self.url, self.get_postdata({'toggle-paid': 'paid'}))
        res = self.client.post(
            self.url, self.get_postdata({'price': self.price.pk,
                                         'allow_inapp': 'False',
                                         'regions': ALL_REGION_IDS}))
        self.assert3xx(res, self.url)
        eq_(self.get_webapp().status, mkt.STATUS_NULL)
        res = self.client.get(self.url)
        pqr = pq(res.content)
        eq_(len(pqr('#paid-island-incomplete:not(.hidden)')), 1)
        eq_(json.loads(pqr('#region-list').attr('data-enabled-provider-ids')),
            [])

    def setup_payment_acct(self, make_owner, user=None, bango_id=123):
        # Set up Solitude return values.
        gen = self.generic_patcher
        prov = self.bango_patcher
        gen.product.get_object.side_effect = ObjectDoesNotExist
        gen.product.post.return_value = {'resource_uri': 'gpuri'}
        prov.product.get_object.side_effect = ObjectDoesNotExist
        prov.product.post.return_value = {
            'resource_uri': 'bpruri', 'bango_id': 123}

        if not user:
            user = self.user

        mkt.set_user(user)

        if make_owner:
            # Make owner.
            user.addonuser_set.get_or_create(addon=self.webapp)

        # Set up an existing bank account.
        seller = SolitudeSeller.objects.create(
            resource_uri='/path/to/sel', user=user, uuid='uuid-%s' % user.pk)
        acct = PaymentAccount.objects.create(
            user=user, uri='asdf-%s' % user.pk, name='test', inactive=False,
            seller_uri='suri-%s' % user.pk, solitude_seller=seller,
            account_id=123, agreed_tos=True)
        return acct, user

    def is_owner(self, user):
        return (self.webapp.authors.filter(
            pk=user.pk, addonuser__role=mkt.AUTHOR_ROLE_OWNER).exists())

    def test_associate_acct_to_app_free_inapp(self):
        acct, user = self.setup_payment_acct(make_owner=True)

        # Must be an app owner to change this.
        assert self.is_owner(user)

        # Associate account with app.
        self.make_premium(self.webapp)
        res = self.client.post(
            self.url, self.get_postdata({'price': 'free',
                                         'allow_inapp': 'True',
                                         'regions': ALL_REGION_IDS,
                                         'accounts': acct.pk}), follow=True)
        self.assertNoFormErrors(res)
        eq_(res.status_code, 200)
        eq_(self.webapp.payment_account(PROVIDER_BANGO).payment_account.pk,
            acct.pk)
        eq_(AddonPremium.objects.all().count(), 0)
        pqr = pq(res.content)
        eq_(len(pqr('#paid-island-incomplete.hidden')), 1)
        eq_(json.loads(pqr('#region-list').attr('data-enabled-provider-ids')),
            [PROVIDER_BANGO])

    def test_associate_acct_to_app(self):
        self.make_premium(self.webapp, price=self.price.price)
        acct, user = self.setup_payment_acct(make_owner=True)
        # Must be an app owner to change this.
        assert self.is_owner(user)
        # Associate account with app.
        for k in [self.generic_patcher.product.get_object_or_404,
                  self.bango_patcher.product.get_object_or_404]:
            k.side_effect = ObjectDoesNotExist

        res = self.client.post(
            self.url, self.get_postdata({'price': self.price.pk,
                                         'accounts': acct.pk,
                                         'regions': ALL_REGION_IDS}),
            follow=True)
        self.assertNoFormErrors(res)
        eq_(res.status_code, 200)
        eq_(len(pq(res.content)('#paid-island-incomplete.hidden')), 1)
        eq_(self.webapp.payment_account(PROVIDER_BANGO).payment_account.pk,
            acct.pk)
        kw = self.generic_patcher.product.post.call_args[1]['data']
        eq_(kw['access'], ACCESS_PURCHASE)
        kw = self.bango_p_patcher.product.post.call_args[1]['data']
        ok_(kw['secret'], kw)

    def test_acct_region_sorting_by_locale(self):
        self.make_premium(self.webapp, price=self.price.price)
        res = self.client.get(self.url + '?lang=en')
        regions = res.context['provider_regions'][PROVIDER_BANGO]
        eq_(regions, [ESP, GBR, USA])
        # Form choices sort in English.
        form_choices = [r[1] for r in
                        res.context['region_form']['regions'].field.choices]
        # For EN, ESP comes before United Kingdom.
        ok_(form_choices.index(ESP.name) < form_choices.index(GBR.name))
        # and United Kingdome comes before United States.
        ok_(form_choices.index(GBR.name) < form_choices.index(USA.name))

    def test_acct_region_sorting_by_locale_fr(self):
        self.make_premium(self.webapp, price=self.price.price)
        res = self.client.get(self.url + '?lang=fr')
        regions = res.context['provider_regions'][PROVIDER_BANGO]
        # En français: Espagne, États-Unis, Royaume-Uni
        # Without unicode normalization this would be:
        # Espagne, Royaume-Uni, États-Unis
        eq_(regions, [ESP, USA, GBR])
        # Check we're also doing a normalized sort of the form choices.
        form_choices = [r[1] for r in
                        res.context['region_form']['regions'].field.choices]
        # For FR, Espagne comes before États-Unis.
        ok_(form_choices.index(ESP.name) < form_choices.index(USA.name))
        # and États-Unis comes before Royaume-Uni.
        ok_(form_choices.index(USA.name) < form_choices.index(GBR.name))

    def test_associate_acct_to_app_when_not_owner(self):
        self.make_premium(self.webapp, price=self.price.price)
        self.login(self.other)
        acct, user = self.setup_payment_acct(make_owner=False, user=self.other)
        # Check we're not an owner before we start.
        assert not self.is_owner(user)

        # Attempt to associate account with app as non-owner.
        res = self.client.post(
            self.url, self.get_postdata({'accounts': acct.pk}), follow=True)
        # Non-owner posts are forbidden.
        eq_(res.status_code, 403)
        # Payment account shouldn't be set as we're not the owner.
        assert not (AddonPaymentAccount.objects
                                       .filter(addon=self.webapp).exists())

    def test_associate_acct_to_app_when_not_owner_and_an_admin(self):
        self.make_premium(self.webapp, self.price.price)
        self.login(self.admin)
        acct, user = self.setup_payment_acct(make_owner=False, user=self.admin)
        # Check we're not an owner before we start.
        assert not self.is_owner(user)
        assert not (AddonPaymentAccount.objects
                                       .filter(addon=self.webapp).exists())
        # Attempt to associate account with app as non-owner admin.
        res = self.client.post(self.url,
                               self.get_postdata({'accounts': acct.pk,
                                                  'price': self.price.pk,
                                                  'regions': ALL_REGION_IDS}),
                               follow=True)
        self.assertFalse(AddonPaymentAccount.objects
                                            .filter(addon=self.webapp)
                                            .exists(),
                         'account was associated')
        pqr = pq(res.content)
        # Payment field should be disabled.
        eq_(len(pqr('#id_form-0-accounts[disabled]')), 1)
        # There's no existing associated account.
        eq_(len(pqr('.current-account')), 0)

    def test_associate_acct_to_app_when_admin_and_owner_acct_exists(self):
        def current_account():
            return self.webapp.payment_account(PROVIDER_BANGO).payment_account

        self.make_premium(self.webapp, price=self.price.price)
        owner_acct, owner_user = self.setup_payment_acct(make_owner=True)

        assert self.is_owner(owner_user)

        self.client.post(self.url,
                         self.get_postdata({'accounts': owner_acct.pk,
                                            'price': self.price.pk,
                                            'regions': ALL_REGION_IDS}),
                         follow=True)
        assert (AddonPaymentAccount.objects
                                   .filter(addon=self.webapp).exists())

        self.login(self.admin)
        admin_acct, admin_user = self.setup_payment_acct(make_owner=False,
                                                         user=self.admin)
        # Check we're not an owner before we start.
        assert not self.is_owner(admin_user)
        assert current_account().pk == owner_acct.pk

        self.client.post(self.url,
                         self.get_postdata({'accounts': admin_acct.pk,
                                            'price': self.price.pk,
                                            'regions': ALL_REGION_IDS}),
                         follow=True)

        assert current_account().pk == owner_acct.pk

    def test_one_owner_and_a_second_one_sees_selected_plus_own_accounts(self):
        self.make_premium(self.webapp, price=self.price.price)
        owner_acct, owner = self.setup_payment_acct(make_owner=True)
        # Should be an owner.
        assert self.is_owner(owner)

        res = self.client.post(
            self.url, self.get_postdata({'accounts': owner_acct.pk,
                                         'price': self.price.pk,
                                         'regions': ALL_REGION_IDS}),
            follow=True)
        assert (AddonPaymentAccount.objects
                                   .filter(addon=self.webapp).exists())

        # Login as other user.
        self.login(self.other)
        owner_acct2, owner2 = self.setup_payment_acct(make_owner=True,
                                                      user=self.other)
        assert self.is_owner(owner2)
        # Should see the saved account plus 2nd owner's own account select
        # and be able to save their own account but not the other owners.
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        pqr = pq(res.content)
        # Check we have just our account option present + '----'.
        eq_(len(pqr('#id_form-0-accounts option')), 2)
        eq_(len(pqr('#id_account[disabled]')), 0)
        eq_(pqr('.current-account').text(), unicode(owner_acct))

        res = self.client.post(
            self.url, self.get_postdata({'accounts': owner_acct2.pk,
                                         'price': self.price.pk,
                                         'regions': ALL_REGION_IDS}),
            follow=True)
        eq_(res.status_code, 200)
        self.assertNoFormErrors(res)
        pqr = pq(res.content)
        eq_(len(pqr('.current-account')), 0)
        eq_(pqr('#id_form-0-accounts option[selected]').text(),
            unicode(owner_acct2))
        # Now there should just be our account.
        eq_(len(pqr('#id_form-0-accounts option')), 1)

    def test_existing_account_should_be_disabled_for_non_owner(self):
        self.make_premium(self.webapp, price=self.price.price)
        acct, user = self.setup_payment_acct(make_owner=True)
        # Must be an app owner to change this.
        assert self.is_owner(user)
        # Associate account with app.
        res = self.client.post(
            self.url, self.get_postdata({'accounts': acct.pk,
                                         'price': self.price.pk,
                                         'regions': ALL_REGION_IDS}),
            follow=True)
        mkt.set_user(self.other)
        # Make this user a dev so they have access to the payments page.
        AddonUser.objects.create(addon=self.webapp,
                                 user=self.other, role=mkt.AUTHOR_ROLE_DEV)
        self.login(self.other)
        # Make sure not an owner.
        assert not self.is_owner(self.other)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        pqr = pq(res.content)
        # No accounts setup.
        eq_(len(pqr('.no-accounts')), len(settings.PAYMENT_PROVIDERS))
        # Currently associated account should be displayed separately.
        eq_(pqr('.current-account').text(), unicode(acct))

    def test_existing_account_should_be_disabled_for_non_owner_admin(self):
        self.make_premium(self.webapp, price=self.price.price)
        # Login as regular user
        self.login(self.other)
        owner_acct, user = self.setup_payment_acct(make_owner=True,
                                                   user=self.other)
        # Must be an app owner to change this.
        assert self.is_owner(self.other)
        # Associate account with app.
        res = self.client.post(self.url,
                               self.get_postdata({'accounts': owner_acct.pk,
                                                  'price': self.price.pk,
                                                  'regions': ALL_REGION_IDS}),
                               follow=True)
        self.assertNoFormErrors(res)
        # Login as admin.
        self.login(self.admin)
        # Create an account as an admin.
        admin_acct, admin_user = self.setup_payment_acct(make_owner=False,
                                                         user=self.admin)
        # Make sure not an owner.
        assert not self.is_owner(self.admin)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        pqr = pq(res.content)
        # Payment field should be disabled.
        eq_(len(pqr('#id_form-0-accounts[disabled]')), 1)
        # Currently associated account should be displayed separately.
        eq_(pqr('.current-account').text(), unicode(owner_acct))

    def test_deleted_payment_accounts_switch_to_incomplete_apps(self):
        self.make_premium(self.webapp, price=self.price.price)
        self.login(self.user)
        addon_account = setup_payment_account(self.webapp, self.user)
        eq_(self.webapp.status, mkt.STATUS_PUBLIC)
        self.client.post(reverse(
            'mkt.developers.provider.delete_payment_account',
            args=[addon_account.payment_account.pk]))
        eq_(self.webapp.reload().status, mkt.STATUS_NULL)

    def test_addon_payment_accounts_with_or_without_addons(self):
        self.make_premium(self.webapp, price=self.price.price)
        self.login(self.user)
        addon_account = setup_payment_account(self.webapp, self.user)
        payment_accounts = reverse('mkt.developers.provider.payment_accounts')
        res = self.client.get(payment_accounts)
        eq_(json.loads(res.content)[0]['app-names'],
            u'Something Something Steamcube!')
        for apa in addon_account.payment_account.addonpaymentaccount_set.all():
            apa.addon.delete()
        res = self.client.get(payment_accounts)
        eq_(json.loads(res.content)[0]['app-names'], u'')

    def setup_bango_portal(self):
        self.user = UserProfile.objects.get(pk=31337)
        self.webapp.update(premium_type=mkt.ADDON_PREMIUM)
        self.login(self.user)
        self.account = setup_payment_account(self.webapp, self.user)
        self.portal_url = self.webapp.get_dev_url(
            'payments.bango_portal_from_addon')

    def test_template_switches(self):
        payments_url = self.webapp.get_dev_url('payments')
        providers = ['reference', 'bango']
        for provider in providers:
            with self.settings(PAYMENT_PROVIDERS=[provider],
                               DEFAULT_PAYMENT_PROVIDER=provider):
                res = self.client.get(payments_url)
            tmpl_id = '#{p}-payment-account-add-template'.format(p=provider)
            tmpl = self.extract_script_template(res.content, tmpl_id)
            eq_(len(tmpl('.payment-account-{p}'.format(p=provider))), 1)

    def test_bango_portal_links(self):
        payments_url = self.webapp.get_dev_url('payments')
        res = self.client.get(payments_url)
        account_template = self.extract_script_template(
            res.content, '#account-row-template')
        eq_(len(account_template('.portal-account')), 1)

    @mock.patch('mkt.developers.views_payments.client.api')
    def test_bango_portal_redirect(self, api):
        self.setup_bango_portal()
        authentication_token = u'D0A44686-D4A3-4B2F-9BEB-5E4975E35192'
        api.bango.login.post.return_value = {
            'person_id': 600925,
            'email_address': u'admin@place.com',
            'authentication_token': authentication_token,
        }
        assert self.is_owner(self.user)
        res = self.client.get(self.portal_url)
        eq_(res.status_code, 204)
        eq_(api.bango.login.post.call_args[0][0]['packageId'],
            int(TEST_PACKAGE_ID))
        redirect_url = res['Location']
        assert authentication_token in redirect_url, redirect_url
        assert 'emailAddress=admin%40place.com' in redirect_url, redirect_url

    @mock.patch('mkt.developers.views_payments.client.api')
    def test_bango_portal_redirect_api_error(self, api):
        self.setup_bango_portal()
        err = {'errors': 'Something went wrong.'}
        api.bango.login.post.side_effect = HttpClientError(content=err)
        res = self.client.get(self.portal_url)
        eq_(res.status_code, 400)
        eq_(json.loads(res.content), err)

    def test_not_bango(self):
        self.setup_bango_portal()
        self.account.payment_account.provider = PROVIDER_REFERENCE
        self.account.payment_account.save()
        res = self.client.get(self.portal_url)
        eq_(res.status_code, 403)

    def test_bango_portal_redirect_role_error(self):
        # Checks that only the owner can access the page (vs. developers).
        self.setup_bango_portal()
        addon_user = self.user.addonuser_set.all()[0]
        addon_user.role = mkt.AUTHOR_ROLE_DEV
        addon_user.save()
        assert not self.is_owner(self.user)
        res = self.client.get(self.portal_url)
        eq_(res.status_code, 403)

    def test_bango_portal_redirect_permission_error(self):
        # Checks that the owner of another app can't access the page.
        self.setup_bango_portal()
        self.login(self.other)
        other_webapp = Webapp.objects.create(status=self.webapp.status,
                                             name='other-%s' % self.webapp.id,
                                             premium_type=mkt.ADDON_PREMIUM)
        AddonUser.objects.create(addon=other_webapp,
                                 user=self.other, role=mkt.AUTHOR_ROLE_OWNER)
        res = self.client.get(self.portal_url)
        eq_(res.status_code, 403)

    def test_bango_portal_redirect_solitude_seller_error(self):
        # Checks that the owner has a SolitudeSeller instance for this app.
        self.setup_bango_portal()
        assert self.is_owner(self.user)
        for acct in self.webapp.app_payment_accounts.all():
            acct.payment_account.solitude_seller.update(user=self.other)
        res = self.client.get(self.portal_url)
        eq_(res.status_code, 403)

    def test_device_checkboxes_present_with_android_payments(self):
        self.create_flag('android-payments')
        self.webapp.update(premium_type=mkt.ADDON_PREMIUM)
        res = self.client.get(self.url)
        pqr = pq(res.content)
        eq_(len(pqr('#paid-android-mobile input[type="checkbox"]')), 1)
        eq_(len(pqr('#paid-android-tablet input[type="checkbox"]')), 1)

    def test_device_checkboxes_present_with_desktop_payments(self):
        self.create_flag('desktop-payments')
        self.webapp.update(premium_type=mkt.ADDON_PREMIUM)
        res = self.client.get(self.url)
        pqr = pq(res.content)
        eq_(len(pqr('#paid-desktop input[type="checkbox"]')), 1)

    def test_device_checkboxes_not_present_without_android_payments(self):
        self.webapp.update(premium_type=mkt.ADDON_PREMIUM)
        res = self.client.get(self.url)
        pqr = pq(res.content)
        eq_(len(pqr('#paid-android-mobile input[type="checkbox"]')), 0)
        eq_(len(pqr('#paid-android-tablet input[type="checkbox"]')), 0)

    def test_cannot_be_paid_with_android_payments_just_ffos(self):
        self.create_flag('android-payments')
        self.webapp.addondevicetype_set.get_or_create(
            device_type=mkt.DEVICE_GAIA.id)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        eq_(res.context['cannot_be_paid'], False)

    def test_cannot_be_paid_without_android_payments_just_ffos(self):
        self.webapp.addondevicetype_set.filter(
            device_type=mkt.DEVICE_GAIA.id).delete()
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        eq_(res.context['cannot_be_paid'], True)

    def test_cannot_be_paid_with_android_payments(self):
        self.create_flag('android-payments')
        for device_type in (mkt.DEVICE_GAIA,
                            mkt.DEVICE_MOBILE, mkt.DEVICE_TABLET):
            self.webapp.addondevicetype_set.get_or_create(
                device_type=device_type.id)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        eq_(res.context['cannot_be_paid'], False)

    def test_cannot_be_paid_with_desktop_payments(self):
        self.create_flag('desktop-payments')
        for device_type in (mkt.DEVICE_GAIA, mkt.DEVICE_DESKTOP):
            self.webapp.addondevicetype_set.get_or_create(
                device_type=device_type.id)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        eq_(res.context['cannot_be_paid'], False)

    def test_cannot_be_paid_without_android_payments(self):
        for device_type in (mkt.DEVICE_GAIA,
                            mkt.DEVICE_MOBILE, mkt.DEVICE_TABLET):
            self.webapp.addondevicetype_set.get_or_create(
                device_type=device_type.id)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        eq_(res.context['cannot_be_paid'], True)

    def test_cannot_be_paid_pkg_with_desktop_pkg(self):
        self.webapp.update(is_packaged=True)
        for device_type in (mkt.DEVICE_GAIA,
                            mkt.DEVICE_DESKTOP):
            self.webapp.addondevicetype_set.get_or_create(
                device_type=device_type.id)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        eq_(res.context['cannot_be_paid'], True)

    def test_cannot_be_paid_pkg_without_desktop_pkg(self):
        self.webapp.update(is_packaged=True)
        self.webapp.addondevicetype_set.get_or_create(
            device_type=mkt.DEVICE_GAIA.id)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        eq_(res.context['cannot_be_paid'], False)

    def test_cannot_be_paid_pkg_with_android_pkg_no_android_payments(self):
        self.webapp.update(is_packaged=True)
        for device_type in (mkt.DEVICE_GAIA,
                            mkt.DEVICE_MOBILE, mkt.DEVICE_TABLET):
            self.webapp.addondevicetype_set.get_or_create(
                device_type=device_type.id)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        eq_(res.context['cannot_be_paid'], True)

    def test_cannot_be_paid_pkg_with_android_pkg_w_android_payments(self):
        self.create_flag('android-payments')
        self.webapp.update(is_packaged=True)
        for device_type in (mkt.DEVICE_GAIA,
                            mkt.DEVICE_MOBILE, mkt.DEVICE_TABLET):
            self.webapp.addondevicetype_set.get_or_create(
                device_type=device_type.id)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        eq_(res.context['cannot_be_paid'], False)

    def test_desktop_if_packaged_desktop(self):
        self.webapp.update(is_packaged=True)
        res = self.client.get(self.url)
        pqr = pq(res.content)
        eq_(len(pqr('#free-desktop')), 1)

    def test_android_if_packaged_android(self):
        self.webapp.update(is_packaged=True)
        res = self.client.get(self.url)
        pqr = pq(res.content)
        eq_(len(pqr('#free-android-mobile')), 1)
        eq_(len(pqr('#free-android-tablet')), 1)


class TestRegions(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141', 'user_admin', 'user_admin_group',
                       'group_admin')

    def setUp(self):
        self.webapp = self.get_webapp()
        AddonDeviceType.objects.create(
            addon=self.webapp, device_type=mkt.DEVICE_GAIA.id)
        self.url = self.webapp.get_dev_url('payments')
        self.login('admin@mozilla.com')
        self.patch = mock.patch('mkt.developers.models.client')
        self.sol = self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def get_webapp(self):
        return Webapp.objects.get(pk=337141)

    def get_dict(self, **kwargs):
        extension = {'regions': mkt.regions.ALL_REGION_IDS,
                     'other_regions': 'on',
                     'free_platforms': ['free-%s' % dt.class_name for dt in
                                        self.webapp.device_types]}
        extension.update(kwargs)
        return extension

    def get_excluded_ids(self):
        return sorted(AER.objects.filter(addon=self.webapp)
                                 .values_list('region', flat=True))

    def test_edit_all_regions_are_not_excluded(self):
        r = self.client.post(self.url, self.get_dict())
        self.assertNoFormErrors(r)
        eq_(AER.objects.count(), 0)


class PaymentsBase(mkt.site.tests.TestCase):
    fixtures = fixture('user_editor', 'user_999')

    def setUp(self):
        self.user = UserProfile.objects.get(pk=999)
        self.login(self.user)
        self.account = self.create()

    def create(self):
        # If user is defined on SolitudeSeller, why do we also need it on
        # PaymentAccount? Fewer JOINs.
        seller = SolitudeSeller.objects.create(user=self.user)
        return PaymentAccount.objects.create(user=self.user,
                                             solitude_seller=seller,
                                             uri='/bango/package/123',
                                             name="cvan's cnotes",
                                             agreed_tos=True)


class TestPaymentAccountsAdd(Patcher, PaymentsBase):
    # TODO: this test provides bare coverage and might need to be expanded.

    def setUp(self):
        super(TestPaymentAccountsAdd, self).setUp()
        self.url = reverse('mkt.developers.provider.add_payment_account')

    def test_login_required(self):
        self.client.logout()
        self.assertLoginRequired(self.client.post(self.url, data={}))

    def test_create(self):
        res = self.client.post(self.url, data={
            'bankAccountPayeeName': 'name',
            'companyName': 'company',
            'vendorName': 'vendor',
            'financeEmailAddress': 'a@a.com',
            'adminEmailAddress': 'a@a.com',
            'supportEmailAddress': 'a@a.com',
            'address1': 'address 1',
            'addressCity': 'city',
            'addressState': 'state',
            'addressZipCode': 'zip',
            'addressPhone': '123',
            'countryIso': 'BRA',
            'currencyIso': 'EUR',
            'bankAccountNumber': '123',
            'bankAccountCode': '123',
            'bankName': 'asd',
            'bankAddress1': 'address 2',
            'bankAddressZipCode': '123',
            'bankAddressIso': 'BRA',
            'account_name': 'account',
            'provider': 'bango',
        })
        eq_(res.status_code, 200)
        output = json.loads(res.content)
        ok_('pk' in output)
        ok_('agreement-url' in output)
        eq_(PaymentAccount.objects.count(), 2)


class TestPaymentAccounts(PaymentsBase):

    def setUp(self):
        super(TestPaymentAccounts, self).setUp()
        self.url = reverse('mkt.developers.provider.payment_accounts')

    def test_login_required(self):
        self.client.logout()
        self.assertLoginRequired(self.client.get(self.url))

    def test_mine(self):
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        output = json.loads(res.content)
        eq_(output[0]['id'], self.account.pk)
        ok_('&#39;' in output[0]['name'])  # Was jinja2 escaped.


class TestPaymentPortal(PaymentsBase):
    fixtures = PaymentsBase.fixtures + fixture('webapp_337141')

    def setUp(self):
        super(TestPaymentPortal, self).setUp()
        self.app_slug = 'something-something'
        self.url = reverse('mkt.developers.provider.payment_accounts')
        self.bango_url = reverse(
            'mkt.developers.apps.payments.bango_portal_from_addon',
            args=[self.app_slug])

    def test_with_app_slug(self):
        res = self.client.get(self.url, {'app-slug': self.app_slug})
        eq_(res.status_code, 200)
        output = json.loads(res.content)
        eq_(output[0]['portal-url'], self.bango_url)

    def test_without_app_slug(self):
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        output = json.loads(res.content)
        eq_(output[0]['portal-url'], '')

    def test_reference(self):
        app_factory(app_slug=self.app_slug)
        PaymentAccount.objects.update(provider=PROVIDER_REFERENCE)
        res = self.client.get(self.bango_url)
        eq_(res.status_code, 403)


class TestPaymentAccount(Patcher, PaymentsBase):

    def setUp(self):
        super(TestPaymentAccount, self).setUp()
        self.url = reverse('mkt.developers.provider.payment_account',
                           args=[self.account.pk])

    def test_login_required(self):
        self.client.logout()
        self.assertLoginRequired(self.client.get(self.url))

    def test_get(self):
        package = mock.Mock()
        package.get.return_value = {'full': {'vendorName': 'testval'}}
        self.bango_patcher.package.return_value = package

        res = self.client.get(self.url)
        self.bango_patcher.package.assert_called_with('123')

        eq_(res.status_code, 200)
        output = json.loads(res.content)
        eq_(output['account_name'], self.account.name)
        assert 'vendorName' in output, (
            'Details from Bango not getting merged in: %s' % output)
        eq_(output['vendorName'], 'testval')


class TestPaymentAgreement(Patcher, PaymentsBase):

    def setUp(self):
        super(TestPaymentAgreement, self).setUp()
        self.url = reverse('mkt.developers.provider.agreement',
                           args=[self.account.pk])

    def test_anon(self):
        self.client.logout()
        self.assertLoginRequired(self.client.get(self.url))

    def test_get_bango_only_provider(self):
        self.bango_patcher.sbi.get_object.return_value = {
            'text': 'blah', 'valid': '2010-08-31T00:00:00'}
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        data = json.loads(res.content)
        eq_(data['text'], 'blah')

    def test_get_bango_multiple_providers(self):
        with self.settings(PAYMENT_PROVIDERS=['bango', 'reference'],
                           DEFAULT_PAYMENT_PROVIDER='reference'):
            self.test_get_bango_only_provider()

    def test_set_bango_only_provider(self):
        self.bango_patcher.sbi.post.return_value = {
            'expires': '2014-08-31T00:00:00',
            'valid': '2014-08-31T00:00:00'}
        res = self.client.post(self.url)
        eq_(res.status_code, 200)
        data = json.loads(res.content)
        eq_(data['valid'], '2014-08-31T00:00:00')

    def test_set_bango_multiple_providers(self):
        with self.settings(PAYMENT_PROVIDERS=['bango', 'reference'],
                           DEFAULT_PAYMENT_PROVIDER='reference'):
            self.test_set_bango_only_provider()


class TestPaymentAccountsForm(PaymentsBase):
    fixtures = PaymentsBase.fixtures + fixture('webapp_337141')

    def setUp(self):
        super(TestPaymentAccountsForm, self).setUp()
        base_url = reverse('mkt.developers.provider.payment_accounts_form')
        self.url = base_url + '?provider=bango&app_slug=something-something'

    def test_login_required(self):
        self.client.logout()
        self.assertLoginRequired(self.client.get(self.url))

    def test_mine(self):
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        eq_(res.context['account_list_form']
               .fields['accounts'].choices.queryset.get(), self.account)

    def test_mine_disagreed_tos(self):
        self.account.update(agreed_tos=False)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        self.assertSetEqual(res.context['account_list_form']
                               .fields['accounts'].choices.queryset.all(), [])


class TestPaymentDelete(PaymentsBase):

    def setUp(self):
        super(TestPaymentDelete, self).setUp()
        self.url = reverse('mkt.developers.provider.delete_payment_account',
                           args=[self.account.pk])

    def test_login_required(self):
        self.client.logout()
        self.assertLoginRequired(self.client.post(self.url, data={}))

    def test_not_mine(self):
        self.login(UserProfile.objects.get(pk=5497308))
        eq_(self.client.post(self.url, data={}).status_code, 404)

    def test_mine(self):
        eq_(self.client.post(self.url, data={}).status_code, 200)
        eq_(PaymentAccount.objects.get(pk=self.account.pk).inactive, True)
