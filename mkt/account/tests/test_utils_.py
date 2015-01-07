from django.test.client import RequestFactory

from nose.tools import eq_

import mkt.site.tests
from mkt.account.utils import purchase_list
from mkt.constants import apps
from mkt.site.fixtures import fixture
from mkt.users.models import UserProfile
from mkt.webapps.models import Installed, Webapp


class TestUtils(mkt.site.tests.TestCase):
    # TODO: add some more tests for purchase_list.
    fixtures = fixture('user_2519', 'webapp_337141')

    def setUp(self):
        self.user = UserProfile.objects.get(pk=2519)
        self.app = Webapp.objects.get(pk=337141)
        self.req = RequestFactory().get('/')

    def _test(self, type, exists):
        Installed.objects.create(user=self.user, addon=self.app,
                                 install_type=type)
        if exists:
            eq_(list(purchase_list(self.req, self.user, None)[0].object_list),
                [self.app])
        else:
            assert not purchase_list(self.req, self.user, None)[0].object_list

    def test_user(self):
        self._test(apps.INSTALL_TYPE_USER, True)

    def test_developer(self):
        self._test(apps.INSTALL_TYPE_DEVELOPER, True)

    def test_reviewer(self):
        self._test(apps.INSTALL_TYPE_REVIEWER, False)
