from nose.tools import eq_

import amo.tests
from mkt.constants.base import LOGIN_SOURCE_FXA
from mkt.site.fixtures import fixture
from mkt.users.management.commands.fxa_mail import get_user_ids
from mkt.users.models import UserProfile


class TestCommand(amo.tests.TestCase):
    fixtures = fixture('user_999', 'webapp_337141')

    def setUp(self):
        self.user = UserProfile.objects.get(pk=999)
        self.developer = UserProfile.objects.get(pk=31337)

    def test_user(self):
        eq_(get_user_ids(False), [999L])
        self.user.update(source=LOGIN_SOURCE_FXA)
        eq_(get_user_ids(False), [])

    def test_developers(self):
        eq_(get_user_ids(True), [31337L])
        self.developer.update(source=LOGIN_SOURCE_FXA)
        eq_(get_user_ids(True), [])

    def test_user_filtered_correctly(self):
        """
        Ensure that if a developer has used FxA, they get correctly filtered
        out for an email sent to users. We do this by setting the FxA source on
        the developer before getting developers.
        """
        self.developer.update(source=LOGIN_SOURCE_FXA)
        eq_(get_user_ids(False), [999L])
