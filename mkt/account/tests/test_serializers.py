from datetime import datetime

import mock
from nose.tools import eq_, ok_

import mkt
import mkt.site.tests
from mkt.account.serializers import (AccountSerializer, AccountInfoSerializer,
                                     TOSSerializer)
from mkt.users.models import UserProfile


class TestAccountSerializer(mkt.site.tests.TestCase):
    def setUp(self):
        self.account = UserProfile()

    def serializer(self):
        return AccountSerializer(instance=self.account)

    def test_display_name_returns_name(self):
        with mock.patch.object(UserProfile, 'name', 'Account name'):
            eq_(self.serializer().data['display_name'], 'Account name')

    def test_recommendations(self):
        # Test default.
        eq_(self.serializer().data['enable_recommendations'], True)
        self.account.enable_recommendations = False
        eq_(self.serializer().data['enable_recommendations'], False)


class TestAccountInfoSerializer(mkt.site.tests.TestCase):
    UNKNOWN = mkt.LOGIN_SOURCE_LOOKUP[mkt.LOGIN_SOURCE_UNKNOWN]
    FIREFOX_ACCOUNTS = mkt.LOGIN_SOURCE_LOOKUP[mkt.LOGIN_SOURCE_FXA]
    PERSONA = mkt.LOGIN_SOURCE_LOOKUP[mkt.LOGIN_SOURCE_BROWSERID]

    def setUp(self):
        self.account = UserProfile()
        self.account.pk = 25

    def serializer(self):
        return AccountInfoSerializer(instance=self.account)

    def test_source_is_a_slug_default(self):
        eq_(self.serializer().data['source'], self.PERSONA)

    def test_source_is_unknown(self):
        self.account.source = mkt.LOGIN_SOURCE_UNKNOWN
        eq_(self.serializer().data['source'], self.PERSONA)

    def test_source_is_fxa(self):
        self.account.source = mkt.LOGIN_SOURCE_FXA
        eq_(self.serializer().data['source'], self.FIREFOX_ACCOUNTS)

    def test_source_is_invalid(self):
        self.account.source = -1
        eq_(self.serializer().data['source'], self.PERSONA)

    def test_source_is_unrelated(self):
        self.account.source = mkt.LOGIN_SOURCE_BROWSERID
        eq_(self.serializer().data['source'], self.PERSONA)

    def test_account_has_no_pk(self):
        self.account.source = mkt.LOGIN_SOURCE_FXA
        self.account.pk = None
        eq_(self.serializer().data['source'], self.UNKNOWN)

    def test_source_is_read_only(self):
        serializer = AccountInfoSerializer(
            instance=None,
            data={'source': mkt.LOGIN_SOURCE_FXA, 'display_name': 'Hey!'},
            partial=True)
        eq_(serializer.is_valid(), True)
        # This works because the model field is `editable=False`.
        eq_(serializer.save().source, mkt.LOGIN_SOURCE_UNKNOWN)

    def test_not_verified(self):
        self.account.is_verified = False
        eq_(self.serializer().data['verified'], False)

    def test_verified(self):
        self.account.is_verified = True
        eq_(self.serializer().data['verified'], True)


class TestTOSSerializer(mkt.site.tests.TestCase):
    def setUp(self):
        self.account = UserProfile()

    def serializer(self, lang='pt-BR'):
        context = {
            'request': mkt.site.tests.req_factory_factory('')
        }
        context['request'].META['ACCEPT_LANGUAGE'] = lang
        context['request'].user = self.account
        return TOSSerializer(instance=self.account, context=context)

    def test_has_signed(self):
        eq_(self.serializer().data['has_signed'], False)
        self.account.read_dev_agreement = datetime.now()
        eq_(self.serializer().data['has_signed'], True)

    def test_tos_url(self):
        ok_('pt-BR' in self.serializer(lang='pt-BR').data['url'])
        ok_('en-US' in self.serializer(lang='foo-LANG').data['url'])
