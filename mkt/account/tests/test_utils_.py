from django.test.client import RequestFactory

from nose.tools import eq_

import mkt
import mkt.site.tests
from mkt.account.utils import purchase_list
from mkt.constants import apps
from mkt.site.fixtures import fixture
from mkt.site.utils import app_factory
from mkt.users.models import UserProfile
from mkt.webapps.models import Webapp


class TestUtils(mkt.site.tests.TestCase):
    fixtures = fixture('user_2519', 'webapp_337141')

    def setUp(self):
        self.user = UserProfile.objects.get(pk=2519)
        self.app = Webapp.objects.get(pk=337141)
        self.req = RequestFactory().get('/')

    def test_user(self):
        self.user.installed_set.create(
            webapp=self.app,
            install_type=apps.INSTALL_TYPE_USER)
        eq_(list(purchase_list(self.req, self.user).object_list), [self.app])

    def test_developer(self):
        self.user.installed_set.create(
            webapp=self.app,
            install_type=apps.INSTALL_TYPE_DEVELOPER)
        eq_(list(purchase_list(self.req, self.user).object_list), [self.app])

    def test_reviewer(self):
        self.user.installed_set.create(
            webapp=self.app,
            install_type=apps.INSTALL_TYPE_REVIEWER)
        eq_(list(purchase_list(self.req, self.user).object_list), [])

    def test_ordering(self):
        self.user.installed_set.create(
            webapp=self.app,
            install_type=apps.INSTALL_TYPE_USER)
        app2 = app_factory()
        self.user.installed_set.create(
            webapp=app2,
            install_type=apps.INSTALL_TYPE_USER)
        eq_(list(purchase_list(self.req, self.user).object_list),
            [app2, self.app])

    def test_contribution_purchase(self):
        self.user.contribution_set.create(
            webapp=self.app,
            type=mkt.CONTRIB_PURCHASE)
        eq_(list(purchase_list(self.req, self.user).object_list), [self.app])

    def test_contribution_refund(self):
        self.user.contribution_set.create(
            webapp=self.app,
            type=mkt.CONTRIB_REFUND)
        eq_(list(purchase_list(self.req, self.user).object_list), [self.app])

    def test_contribution_chargeback(self):
        self.user.contribution_set.create(
            webapp=self.app,
            type=mkt.CONTRIB_CHARGEBACK)
        eq_(list(purchase_list(self.req, self.user).object_list), [self.app])

    def test_contribution_installed_same_app(self):
        self.user.installed_set.create(
            webapp=self.app,
            install_type=apps.INSTALL_TYPE_USER)
        self.user.contribution_set.create(
            webapp=self.app,
            type=mkt.CONTRIB_PURCHASE)
        eq_(list(purchase_list(self.req, self.user).object_list), [self.app])
