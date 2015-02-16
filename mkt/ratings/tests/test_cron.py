# -*- coding: utf-8 -*-
from django.conf import settings
from django.core import mail
from django.utils.encoding import smart_str

import mock
from nose.tools import eq_

import mkt.site.tests
from mkt.ratings.cron import email_daily_ratings
from mkt.ratings.models import Review
from mkt.site.fixtures import fixture
from mkt.webapps.models import AddonUser
from mkt.users.models import UserProfile


@mock.patch.object(settings, 'SEND_REAL_EMAIL', True)
class TestEmailDailyRatings(mkt.site.tests.TestCase):
    fixtures = fixture('users')

    def setUp(self):
        self.app = mkt.site.tests.app_factory(name='test')
        self.app2 = mkt.site.tests.app_factory(name='test2')

        self.user = UserProfile.objects.get(email='regular@mozilla.com')
        AddonUser.objects.create(addon=self.app, user=self.user)
        AddonUser.objects.create(addon=self.app2, user=self.user)

    def test_emails_goes_out(self):
        self.app1_review = Review.objects.create(
            addon=self.app, user=self.user, rating=1,
            body='sux, I want my money back.')
        self.app1_review.update(created=self.days_ago(1))

        email_daily_ratings()
        eq_(len(mail.outbox), 1)
        eq_(mail.outbox[0].to, [self.user.email])
        eq_(str(self.app1_review.body) in smart_str(mail.outbox[0].body), True)

    def test_one_email_for_multiple_reviews(self):
        self.app2_review = Review.objects.create(
            addon=self.app2, user=self.user, rating=4,
            body='waste of two seconds of my life.')
        self.app2_review.update(created=self.days_ago(1))

        self.app2_review2 = Review.objects.create(
            addon=self.app2, user=self.user, rating=5,
            body='a++ would play again')
        self.app2_review2.update(created=self.days_ago(1))

        email_daily_ratings()
        eq_(len(mail.outbox), 1)
        eq_(mail.outbox[0].to, [self.user.email])
        eq_(str(self.app2_review.body) in smart_str(mail.outbox[0].body), True)
        eq_(str(self.app2_review2.body) in smart_str(mail.outbox[0].body),
            True)
