import mock
from nose.tools import eq_

import amo
import amo.tests
from mkt.account.serializers import AccountSerializer, AccountInfoSerializer
from mkt.users.models import UserProfile


class TestAccountSerializer(amo.tests.TestCase):
    def setUp(self):
        self.account = UserProfile()

    def serializer(self):
        return AccountSerializer(instance=self.account)

    def test_display_name_returns_name(self):
        with mock.patch.object(UserProfile, 'name', 'Account name'):
            eq_(self.serializer().data['display_name'], 'Account name')

    def test_not_verified(self):
        self.account.is_verified = False
        eq_(self.serializer().data['verified'], False)

    def test_verified(self):
        self.account.is_verified = True
        eq_(self.serializer().data['verified'], True)


class TestAccountInfoSerializer(amo.tests.TestCase):
    UNKNOWN = amo.LOGIN_SOURCE_LOOKUP[amo.LOGIN_SOURCE_UNKNOWN]
    FIREFOX_ACCOUNTS = amo.LOGIN_SOURCE_LOOKUP[amo.LOGIN_SOURCE_FXA]

    def setUp(self):
        self.account = UserProfile()

    def serializer(self):
        return AccountInfoSerializer(instance=self.account)

    def test_source_is_a_slug_default(self):
        eq_(self.serializer().data['source'], self.UNKNOWN)

    def test_source_is_fxa(self):
        self.account.source = amo.LOGIN_SOURCE_FXA
        eq_(self.serializer().data['source'], self.FIREFOX_ACCOUNTS)

    def test_source_is_invalid(self):
        self.account.source = -1
        eq_(self.serializer().data['source'], self.UNKNOWN)

    def test_source_is_read_only(self):
        serializer = AccountInfoSerializer(
            instance=None,
            data={'source': amo.LOGIN_SOURCE_FXA, 'display_name': 'Hey!'},
            partial=True)
        eq_(serializer.is_valid(), True)
        # This works because the model field is `editable=False`.
        eq_(serializer.save().source, amo.LOGIN_SOURCE_UNKNOWN)
