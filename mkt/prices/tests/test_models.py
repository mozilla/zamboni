import datetime
from decimal import Decimal

from django.utils import translation

import mock
from nose.tools import eq_, ok_

import mkt
import mkt.site.tests
from mkt.constants import apps
from mkt.constants.payments import PROVIDER_BANGO, PROVIDER_REFERENCE
from mkt.constants.regions import (
    ALL_REGION_IDS, BRA, ESP, HUN, RESTOFWORLD, USA)
from mkt.prices.models import WebappPremium, Price, PriceCurrency, Refund
from mkt.purchase.models import Contribution
from mkt.site.fixtures import fixture
from mkt.users.models import UserProfile
from mkt.webapps.models import WebappUser, Webapp


class TestPremium(mkt.site.tests.TestCase):
    fixtures = fixture('prices2', 'webapp_337141')

    def setUp(self):
        self.tier_one = Price.objects.get(pk=1)
        self.webapp = Webapp.objects.get(pk=337141)

    def test_is_complete(self):
        self.webapp.support_email = 'foo@example.com'
        ap = WebappPremium(webapp=self.webapp)
        assert not ap.is_complete()
        ap.price = self.tier_one
        assert ap.is_complete()


class TestPrice(mkt.site.tests.TestCase):
    fixtures = fixture('prices2')

    def setUp(self):
        self.tier_one = Price.objects.get(pk=1)
        if hasattr(Price, '_currencies'):
            del Price._currencies  # needed to pick up fixtures.

    def test_active(self):
        Price.objects.get(pk=2).update(active=False)
        eq_(Price.objects.count(), 2)
        eq_(Price.objects.active().count(), 1)

    def test_active_order(self):
        Price.objects.get(pk=2).update(active=False)
        Price.objects.create(name='USD', price='0.00')
        Price.objects.create(name='USD', price='1.99')
        eq_(list(Price.objects.active().values_list('price', flat=True)),
            [Decimal('0.00'), Decimal('0.99'), Decimal('1.99')])

    def test_method_default_all(self):
        price = Price.objects.create(name='USD', price='0.00')
        eq_(price.method, 2)

    def test_method_specified(self):
        price = Price.objects.create(name='USD', price='0.99', method=0)
        eq_(price.method, 0)

    def test_currency(self):
        eq_(self.tier_one.pricecurrency_set.count(), 3)

    def test_get(self):
        eq_(Price.objects.get(pk=1).get_price(regions=[RESTOFWORLD.id]),
            Decimal('0.99'))

    def test_get_tier(self):
        translation.activate('en_CA')
        eq_(Price.objects.get(pk=1).get_price(regions=[RESTOFWORLD.id]),
            Decimal('0.99'))
        eq_(Price.objects.get(pk=1).get_price_locale(regions=[RESTOFWORLD.id]),
            u'US$0.99')

    def test_get_tier_and_locale(self):
        translation.activate('pt_BR')
        eq_(Price.objects.get(pk=2).get_price(regions=[RESTOFWORLD.id]),
            Decimal('1.99'))
        eq_(Price.objects.get(pk=2).get_price_locale(regions=[RESTOFWORLD.id]),
            u'US$1,99')

    def test_no_region(self):
        eq_(Price.objects.get(pk=2).get_price_locale(regions=[HUN.id]), None)

    def test_fallback(self):
        translation.activate('foo')
        eq_(Price.objects.get(pk=1).get_price(regions=[RESTOFWORLD.id]),
            Decimal('0.99'))
        eq_(Price.objects.get(pk=1).get_price_locale(regions=[RESTOFWORLD.id]),
            u'$0.99')

    def test_transformer(self):
        price = Price.objects.get(pk=1)
        price.get_price_locale(regions=[RESTOFWORLD.id])
        # Warm up Price._currencies.
        with self.assertNumQueries(0):
            eq_(price.get_price_locale(regions=[RESTOFWORLD.id]), u'$0.99')

    def test_get_tier_price(self):
        eq_(Price.objects.get(pk=2).get_price_locale(regions=[BRA.id]),
            'R$1.01')

    def test_get_tier_price_provider(self):
        # Turning on Reference will give USA the tier.
        PriceCurrency.objects.get(pk=3).update(provider=PROVIDER_REFERENCE)
        eq_(Price.objects.get(pk=2)
            .get_price_locale(regions=[BRA.id], provider=PROVIDER_REFERENCE),
            'R$1.01')

    def test_get_free_tier_price(self):
        price = self.make_price('0.00')
        eq_(price.get_price_locale(regions=[USA.id]), '$0.00')

    def test_euro_placement_en(self):
        with self.activate('en-us'):
            eq_(Price.objects.get(pk=2).get_price_locale(regions=[ESP.id]),
                u'\u20ac0.50')

    def test_euro_placement_es(self):
        with self.activate('es'):
            eq_(Price.objects.get(pk=2).get_price_locale(regions=[ESP.id]),
                u'0,50\xa0\u20ac')

    def test_euro_placement_nl(self):
        with self.activate('nl'):
            eq_(Price.objects.get(pk=2).get_price_locale(regions=[ESP.id]),
                u'\u20ac\xa00,50')

    def test_prices(self):
        currencies = Price.objects.get(pk=1).prices()
        eq_(len(currencies), 2)
        eq_(currencies[0]['currency'], 'PLN')

    def test_wrong_currency(self):
        bad = 4999
        ok_(bad not in ALL_REGION_IDS)
        ok_(not Price.objects.get(pk=1).get_price('foo', regions=[bad]))

    def test_prices_provider(self):
        currencies = Price.objects.get(pk=1).prices(
            provider=PROVIDER_REFERENCE)
        eq_(len(currencies), 2)

    def test_multiple_providers(self):
        PriceCurrency.objects.get(pk=2).update(provider=PROVIDER_REFERENCE)
        # This used to be 0, so changing it to 3 puts in scope of the filter.
        with self.settings(PAYMENT_PROVIDERS=['reference', 'bango']):
            currencies = Price.objects.get(pk=1).prices()
            eq_(len(currencies), 3)

    def test_region_ids_by_name_multi_provider(self):
        with self.settings(PAYMENT_PROVIDERS=['reference', 'bango']):
            eq_(Price.objects.get(pk=2).region_ids_by_name(),
                [BRA.id, ESP.id, RESTOFWORLD.id])

    def test_region_ids_by_name(self):
        eq_(Price.objects.get(pk=2).region_ids_by_name(),
            [BRA.id, ESP.id, RESTOFWORLD.id])

    def test_region_ids_by_name_w_provider_reference(self):
        eq_(Price.objects.get(pk=2).region_ids_by_name(
            provider=PROVIDER_REFERENCE), [BRA.id, ESP.id, RESTOFWORLD.id])

    def test_provider_regions(self):
        with self.settings(PAYMENT_PROVIDERS=['reference', 'bango']):
            eq_(Price.objects.get(pk=2).provider_regions(), {
                PROVIDER_REFERENCE: [BRA, ESP, RESTOFWORLD],
                PROVIDER_BANGO: []})

    def test_provider_regions_reference(self):
        with self.settings(PAYMENT_PROVIDERS=['reference']):
            eq_(Price.objects.get(pk=2).provider_regions(), {
                PROVIDER_REFERENCE: [BRA, ESP, RESTOFWORLD]})


class TestPriceCurrencyChanges(mkt.site.tests.TestCase):

    def setUp(self):
        self.webapp = mkt.site.tests.app_factory()
        self.make_premium(self.webapp)
        self.currency = self.webapp.premium.price.pricecurrency_set.all()[0]

    @mock.patch('mkt.webapps.tasks.index_webapps')
    def test_save(self, index_webapps):
        self.currency.save()
        eq_(index_webapps.delay.call_args[0][0], [self.webapp.pk])

    @mock.patch('mkt.webapps.tasks.index_webapps')
    def test_delete(self, index_webapps):
        self.currency.delete()
        eq_(index_webapps.delay.call_args[0][0], [self.webapp.pk])


class ContributionMixin(object):

    def setUp(self):
        self.webapp = Webapp.objects.get(pk=337141)
        self.user = UserProfile.objects.get(pk=999)

    def create(self, type):
        return Contribution.objects.create(type=type, webapp=self.webapp,
                                           user=self.user)

    def purchased(self):
        return (self.webapp.webapppurchase_set
                .filter(user=self.user, type=mkt.CONTRIB_PURCHASE)
                .exists())

    def type(self):
        return self.webapp.webapppurchase_set.get(user=self.user).type


class TestContribution(ContributionMixin, mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141', 'user_999', 'user_admin')

    def test_purchase(self):
        self.create(mkt.CONTRIB_PURCHASE)
        assert self.purchased()

    def test_refund(self):
        self.create(mkt.CONTRIB_REFUND)
        assert not self.purchased()

    def test_purchase_and_refund(self):
        self.create(mkt.CONTRIB_PURCHASE)
        self.create(mkt.CONTRIB_REFUND)
        assert not self.purchased()
        eq_(self.type(), mkt.CONTRIB_REFUND)

    def test_refund_and_purchase(self):
        # This refund does nothing, there was nothing there to refund.
        self.create(mkt.CONTRIB_REFUND)
        self.create(mkt.CONTRIB_PURCHASE)
        assert self.purchased()
        eq_(self.type(), mkt.CONTRIB_PURCHASE)

    def test_really_cant_decide(self):
        self.create(mkt.CONTRIB_PURCHASE)
        self.create(mkt.CONTRIB_REFUND)
        self.create(mkt.CONTRIB_PURCHASE)
        self.create(mkt.CONTRIB_REFUND)
        self.create(mkt.CONTRIB_PURCHASE)
        assert self.purchased()
        eq_(self.type(), mkt.CONTRIB_PURCHASE)

    def test_purchase_and_chargeback(self):
        self.create(mkt.CONTRIB_PURCHASE)
        self.create(mkt.CONTRIB_CHARGEBACK)
        assert not self.purchased()
        eq_(self.type(), mkt.CONTRIB_CHARGEBACK)

    def test_other_user(self):
        other = UserProfile.objects.get(email='admin@mozilla.com')
        Contribution.objects.create(type=mkt.CONTRIB_PURCHASE,
                                    webapp=self.webapp, user=other)
        self.create(mkt.CONTRIB_PURCHASE)
        self.create(mkt.CONTRIB_REFUND)
        eq_(self.webapp.webapppurchase_set.filter(user=other).count(), 1)

    def set_role(self, role):
        WebappUser.objects.create(webapp=self.webapp, user=self.user,
                                  role=role)
        self.create(mkt.CONTRIB_PURCHASE)
        installed = self.user.installed_set.filter(webapp=self.webapp)
        eq_(installed.count(), 1)
        eq_(installed[0].install_type, apps.INSTALL_TYPE_DEVELOPER)

    def test_user_dev(self):
        self.set_role(mkt.AUTHOR_ROLE_DEV)

    def test_user_owner(self):
        self.set_role(mkt.AUTHOR_ROLE_OWNER)

    def test_user_installed_dev(self):
        self.create(mkt.CONTRIB_PURCHASE)
        eq_(self.user.installed_set.filter(webapp=self.webapp).count(), 1)

    def test_user_not_purchased(self):
        self.webapp.update(premium_type=mkt.WEBAPP_PREMIUM)
        eq_(list(self.user.purchase_ids()), [])

    def test_user_purchased(self):
        self.webapp.update(premium_type=mkt.WEBAPP_PREMIUM)
        self.webapp.webapppurchase_set.create(user=self.user)
        eq_(list(self.user.purchase_ids()), [337141L])

    def test_user_refunded(self):
        self.webapp.update(premium_type=mkt.WEBAPP_PREMIUM)
        self.webapp.webapppurchase_set.create(user=self.user,
                                              type=mkt.CONTRIB_REFUND)
        eq_(list(self.user.purchase_ids()), [])

    def test_user_cache(self):
        # Tests that the purchase_ids caches.
        self.webapp.update(premium_type=mkt.WEBAPP_PREMIUM)
        eq_(list(self.user.purchase_ids()), [])
        self.create(mkt.CONTRIB_PURCHASE)
        eq_(list(self.user.purchase_ids()), [337141L])
        # This caches.
        eq_(list(self.user.purchase_ids()), [337141L])
        self.create(mkt.CONTRIB_REFUND)
        eq_(list(self.user.purchase_ids()), [])


class TestRefundContribution(ContributionMixin, mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141', 'user_999', 'user_admin')

    def setUp(self):
        super(TestRefundContribution, self).setUp()
        self.contribution = self.create(mkt.CONTRIB_PURCHASE)

    def do_refund(self, expected, status, refund_reason=None,
                  rejection_reason=None):
        """Checks that a refund is enqueued and contains the correct values."""
        self.contribution.enqueue_refund(status, self.user,
                                         refund_reason=refund_reason,
                                         rejection_reason=rejection_reason)
        expected.update(contribution=self.contribution, status=status)
        eq_(Refund.objects.count(), 1)
        refund = Refund.objects.filter(**expected)
        eq_(refund.exists(), True)
        return refund[0]

    def test_pending(self):
        reason = 'this is bloody bullocks, mate'
        expected = dict(refund_reason=reason,
                        requested__isnull=False,
                        approved=None,
                        declined=None)
        refund = self.do_refund(expected, mkt.REFUND_PENDING, reason)
        self.assertCloseToNow(refund.requested)

    def test_pending_to_approved(self):
        reason = 'this is bloody bullocks, mate'
        expected = dict(refund_reason=reason,
                        requested__isnull=False,
                        approved=None,
                        declined=None)
        refund = self.do_refund(expected, mkt.REFUND_PENDING, reason)
        self.assertCloseToNow(refund.requested)

        # Change `requested` date to some date in the past.
        requested_date = refund.requested - datetime.timedelta(hours=1)
        refund.requested = requested_date
        refund.save()

        expected = dict(refund_reason=reason,
                        requested__isnull=False,
                        approved__isnull=False,
                        declined=None)
        refund = self.do_refund(expected, mkt.REFUND_APPROVED)
        eq_(refund.requested, requested_date,
            'Expected date `requested` to remain unchanged.')
        self.assertCloseToNow(refund.approved)

    def test_approved_instant(self):
        expected = dict(refund_reason='',
                        requested__isnull=False,
                        approved__isnull=False,
                        declined=None)
        refund = self.do_refund(expected, mkt.REFUND_APPROVED_INSTANT)
        self.assertCloseToNow(refund.requested)
        self.assertCloseToNow(refund.approved)

    def test_pending_to_declined(self):
        refund_reason = 'please, bro'
        rejection_reason = 'sorry, brah'

        expected = dict(refund_reason=refund_reason,
                        rejection_reason='',
                        requested__isnull=False,
                        approved=None,
                        declined=None)
        refund = self.do_refund(expected, mkt.REFUND_PENDING, refund_reason)
        self.assertCloseToNow(refund.requested)

        requested_date = refund.requested - datetime.timedelta(hours=1)
        refund.requested = requested_date
        refund.save()

        expected = dict(refund_reason=refund_reason,
                        rejection_reason=rejection_reason,
                        requested__isnull=False,
                        approved=None,
                        declined__isnull=False)
        refund = self.do_refund(expected, mkt.REFUND_DECLINED,
                                rejection_reason=rejection_reason)
        eq_(refund.requested, requested_date,
            'Expected date `requested` to remain unchanged.')
        self.assertCloseToNow(refund.declined)


class TestRefundManager(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141', 'user_999', 'user_admin')

    def setUp(self):
        self.webapp = Webapp.objects.get(id=337141)
        self.user = UserProfile.objects.get(id=999)
        self.expected = {}
        for status in mkt.REFUND_STATUSES.keys():
            c = Contribution.objects.create(webapp=self.webapp, user=self.user,
                                            type=mkt.CONTRIB_PURCHASE)
            self.expected[status] = Refund.objects.create(contribution=c,
                                                          status=status,
                                                          user=self.user)

    def test_all(self):
        eq_(sorted(Refund.objects.values_list('id', flat=True)),
            sorted(e.id for e in self.expected.values()))

    def test_pending(self):
        eq_(list(Refund.objects.pending(self.webapp)),
            [self.expected[mkt.REFUND_PENDING]])

    def test_approved(self):
        eq_(list(Refund.objects.approved(self.webapp)),
            [self.expected[mkt.REFUND_APPROVED]])

    def test_instant(self):
        eq_(list(Refund.objects.instant(self.webapp)),
            [self.expected[mkt.REFUND_APPROVED_INSTANT]])

    def test_declined(self):
        eq_(list(Refund.objects.declined(self.webapp)),
            [self.expected[mkt.REFUND_DECLINED]])

    def test_by_webapp(self):
        other = Webapp.objects.create()
        c = Contribution.objects.create(webapp=other, user=self.user,
                                        type=mkt.CONTRIB_PURCHASE)
        ref = Refund.objects.create(contribution=c, status=mkt.REFUND_DECLINED,
                                    user=self.user)

        declined = Refund.objects.filter(status=mkt.REFUND_DECLINED)
        eq_(sorted(r.id for r in declined),
            sorted(r.id for r in [self.expected[mkt.REFUND_DECLINED], ref]))

        eq_(sorted(r.id for r in Refund.objects.by_webapp(webapp=self.webapp)),
            sorted(r.id for r in self.expected.values()))
        eq_(list(Refund.objects.by_webapp(webapp=other)), [ref])
