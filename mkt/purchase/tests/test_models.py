# -*- coding: utf-8 -*-
from django.conf import settings
from django.core import mail

from nose.tools import eq_

import amo
import amo.tests
from mkt.prices.models import Refund
from mkt.purchase.models import Contribution
from mkt.webapps.models import Addon
from mkt.users.models import UserProfile
from mkt.site.fixtures import fixture


class TestEmail(amo.tests.TestCase):
    fixtures = fixture('user_999', 'webapp_337141')

    def setUp(self):
        self.addon = Addon.objects.get(pk=337141)
        self.user = UserProfile.objects.get(pk=999)

    def make_contribution(self, amount, locale, type):
        return Contribution.objects.create(type=type, addon=self.addon,
                                           user=self.user, amount=amount,
                                           source_locale=locale)

    def notification_email(self, amount, locale, method):
        cont = self.make_contribution(amount, locale, amo.CONTRIB_REFUND)
        getattr(cont, method)()
        eq_(len(mail.outbox), 1)
        return mail.outbox[0]

    def test_accepted_email(self):
        email = self.notification_email('10', 'en-US', 'mail_approved')
        eq_(email.subject, u'%s refund approved' % self.addon.name)
        assert str(self.addon.name) in email.body

    def test_accepted_unicode(self):
        self.addon.name = u'Азәрбајҹан'
        self.addon.save()
        email = self.notification_email('10', 'en-US', 'mail_approved')
        assert '$10.00' in email.body

    def test_accepted_locale(self):
        self.addon.name = {'fr': u'België'}
        self.addon.locale = 'fr'
        self.addon.save()
        email = self.notification_email('-10', 'fr', 'mail_approved')
        assert u'België' in email.body
        assert u'10,00\xa0$US' in email.body

    def test_declined_email(self):
        email = self.notification_email('10', 'en-US', 'mail_declined')
        eq_(email.subject, u'%s refund declined' % self.addon.name)

    def test_declined_unicode(self):
        self.addon.name = u'Азәрбајҹан'
        self.addon.save()
        email = self.notification_email('10', 'en-US', 'mail_declined')
        eq_(email.subject, u'%s refund declined' % self.addon.name)

    def test_failed_email(self):
        UserProfile.objects.get_or_create(id=settings.TASK_USER_ID)
        cont = self.make_contribution('10', 'en-US', amo.CONTRIB_PURCHASE)
        msg = 'oh no'
        cont.record_failed_refund(msg, self.user)
        eq_(Refund.objects.count(), 1)
        rf = Refund.objects.get(contribution=cont)
        eq_(rf.status, amo.REFUND_FAILED)
        eq_(rf.rejection_reason, msg)
        eq_(len(mail.outbox), 2)
        usermail, devmail = mail.outbox
        eq_(usermail.to, [self.user.email])
        eq_(devmail.to, [self.addon.support_email])
        assert msg in devmail.body
