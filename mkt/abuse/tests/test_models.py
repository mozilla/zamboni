from django.conf import settings
from django.core import mail

from nose.tools import eq_

import amo.tests
from mkt.abuse.models import AbuseReport
from mkt.site.fixtures import fixture
from mkt.webapps.models import Webapp
from mkt.users.models import UserProfile


class TestAbuse(amo.tests.TestCase):
    fixtures = fixture('user_999', 'webapp_337141')

    def setUp(self):
        self.app = Webapp.objects.get(pk=337141)
        self.user = UserProfile.objects.get(pk=999)

    def test_user(self):
        AbuseReport(user=self.user).send()
        assert mail.outbox[0].subject.startswith('[User]')
        eq_(mail.outbox[0].to, [settings.ABUSE_EMAIL])

    def test_addon(self):
        AbuseReport(addon=self.app).send()
        assert mail.outbox[0].subject.startswith('[App]')

    def test_addon_fr(self):
        with self.activate(locale='fr'):
            AbuseReport(addon=self.app).send()
        assert mail.outbox[0].subject.startswith('[App]')
