# -*- coding: utf-8 -*-
import json

from django.core import mail
from django.test.client import RequestFactory

import phpserialize as php
from nose.tools import eq_

import amo
import amo.tests
from addons.models import Addon
from stats.models import ClientData, Contribution
from stats.db import StatsDictField
from users.models import UserProfile
from market.models import Refund
from zadmin.models import DownloadSource

import mkt.regions


class TestStatsDictField(amo.tests.TestCase):

    def test_to_python_none(self):
        eq_(StatsDictField().to_python(None), None)

    def test_to_python_dict(self):
        eq_(StatsDictField().to_python({'a': 1}), {'a': 1})

    def test_to_python_php(self):
        val = {'a': 1}
        eq_(StatsDictField().to_python(php.serialize(val)), val)

    def test_to_python_json(self):
        val = {'a': 1}
        eq_(StatsDictField().to_python(json.dumps(val)), val)


class TestEmail(amo.tests.TestCase):
    fixtures = ['base/users', 'base/addon_3615']

    def setUp(self):
        self.addon = Addon.objects.get(pk=3615)
        self.user = UserProfile.objects.get(pk=999)

    def make_contribution(self, amount, locale, type):
        return Contribution.objects.create(type=type, addon=self.addon,
                                           user=self.user, amount=amount,
                                           source_locale=locale)

    def chargeback_email(self, amount, locale):
        cont = self.make_contribution(amount, locale, amo.CONTRIB_CHARGEBACK)
        cont.mail_chargeback()
        eq_(len(mail.outbox), 1)
        return mail.outbox[0]

    def test_chargeback_email(self):
        email = self.chargeback_email('10', 'en-US')
        eq_(email.subject, u'%s payment reversal' % self.addon.name)
        assert str(self.addon.name) in email.body

    def test_chargeback_negative(self):
        email = self.chargeback_email('-10', 'en-US')
        assert '$10.00' in email.body

    def test_chargeback_positive(self):
        email = self.chargeback_email('10', 'en-US')
        assert '$10.00' in email.body

    def test_chargeback_unicode(self):
        self.addon.name = u'Азәрбајҹан'
        self.addon.save()
        email = self.chargeback_email('-10', 'en-US')
        assert '$10.00' in email.body

    def test_chargeback_locale(self):
        self.addon.name = {'fr': u'België'}
        self.addon.locale = 'fr'
        self.addon.save()
        email = self.chargeback_email('-10', 'fr')
        assert u'België' in email.body
        assert u'10,00\xa0$US' in email.body

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


class TestClientData(amo.tests.TestCase):

    def test_get_or_create(self):
        download_source = DownloadSource.objects.create(name='mkt-home')
        device_type = 'desktop'
        user_agent = 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:16.0)'
        client = RequestFactory()
        request = client.post('/somewhere',
                              data={'src': download_source.name,
                                    'device_type': device_type,
                                    'is_chromeless': False},
                              **{'HTTP_USER_AGENT': user_agent})

        cli = ClientData.get_or_create(request)
        eq_(cli.download_source, download_source)
        eq_(cli.device_type, device_type)
        eq_(cli.user_agent, user_agent)
        eq_(cli.is_chromeless, False)
        eq_(cli.language, 'en-us')
        eq_(cli.region, mkt.regions.RESTOFWORLD.id)
