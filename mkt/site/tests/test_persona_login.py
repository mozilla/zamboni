import collections
import json
from datetime import datetime
from urlparse import urlparse

from django.conf import settings
from django.core.urlresolvers import reverse

from mock import ANY, Mock, patch
from nose.tools import eq_

import amo
from mkt.access.models import Group, GroupUser
from mkt.users.models import UserProfile
from mkt.users.views import browserid_authenticate


def fake_request():
    request = Mock()
    request.LANG = 'foo'
    request.GET = request.META = {}
    # Fake out host/scheme for Persona login.
    request.get_host.return_value = urlparse(settings.SITE_URL).netloc
    request.is_secure.return_value = False
    return request


class FakeResponse(object):
    def __init__(self, status_code, data):
        self.status_code = status_code
        self.data = data

    def json(self):
        return self.data

class TestPersonaLogin(amo.tests.TestCase):
    fixtures = ('users/test_backends',)

    def setUp(self):
        super(TestPersonaLogin, self).setUp()
        self.client = amo.tests.TestClient()
        self.client.get('/')
        self.user = UserProfile.objects.get(id='4043307')
        self.url = reverse('users.browserid_login')
        self.data = {'username': 'jbalogh@mozilla.com', 'password': 'foo'}

    @patch('requests.post')
    def test_browserid_login_success(self, http_request):
        """
        A success response from BrowserID results in successful login.
        """
        url = reverse('users.browserid_login')
        http_request.return_value = FakeResponse(
            200,
            {'status': 'okay',
             'email': 'jbalogh@mozilla.com'})
        res = self.client.post(url, data=dict(assertion='fake-assertion',
                                              audience='fakeamo.org'))
        eq_(res.status_code, 200)

        # If they're already logged in we return fast.
        eq_(self.client.post(url).status_code, 200)

    @patch('requests.post')
    def test_browserid_unverified_login_success(self, http_request):
        """A success response from BrowserID results in a successful login."""

        # Preverified accounts should not be accessible to unverified
        # logins.
        http_request.return_value = FakeResponse(
            200,
            {'status': 'okay', 'unverified-email': 'jbalogh@mozilla.com'})
        res = self.client.post(self.url, {'assertion': 'fake-assertion',
                                          'audience': 'fakeamo.org'})
        eq_(res.status_code, 401)
        eq_(self.user.reload().is_verified, True)

        # A completely unverified address should be able to log in.
        self.user.update(is_verified=False)
        http_request.return_value = FakeResponse(
            200,
            {'status': 'okay', 'unverified-email': 'unverified@example.org'})
        res = self.client.post(self.url, {'assertion': 'fake-assertion',
                                          'audience': 'fakeamo.org'})
        eq_(res.status_code, 200)
        eq_(self.user.reload().is_verified, False)

        # If the user is already logged in, then we return fast.
        eq_(self.client.post(self.url).status_code, 200)

    @patch('mkt.users.models.UserProfile.log_login_attempt')
    @patch('requests.post')
    def test_browserid_login_logged(self, http_request, log_login_attempt):
        url = reverse('users.browserid_login')
        http_request.return_value = FakeResponse(
            200,
            {'status': 'okay', 'email': 'jbalogh@mozilla.com'})
        self.client.post(url, data=dict(assertion='fake-assertion',
                                        audience='fakeamo.org'))
        log_login_attempt.assert_called_once_with(True)

    def _make_admin_user(self, email):
        """
        Create a user with at least one admin privilege.
        """
        p = UserProfile.objects.create(
            username='admin', email=email,
            password='hunter2', created=datetime.now(), pk=998)
        admingroup = Group.objects.create(rules='Users:Edit')
        GroupUser.objects.create(group=admingroup, user=p)

    def _browserid_login(self, email, http_request):
        http_request.return_value = FakeResponse(
                200, {'status': 'okay', 'email': email})
        return self.client.post(reverse('users.browserid_login'),
                                data=dict(assertion='fake-assertion',
                                          audience='fakeamo.org'))

    @patch('requests.post')
    def test_browserid_restricted_login(self, http_request):
        """
        A success response from BrowserID for accounts restricted to
        password login results in a 400 error, for which the frontend
        will display a message about the restriction.
        """
        email = 'admin@mozilla.com'
        self._make_admin_user(email)
        res = self._browserid_login(email, http_request)
        eq_(res.status_code, 200)

    @patch('requests.post')
    @patch('mkt.users.views.record_action')
    def test_browserid_no_account(self, record_action, http_request):
        """
        BrowserID login for an email address with no account creates a
        new account.
        """
        email = 'newuser@example.com'
        res = self._browserid_login(email, http_request)
        eq_(res.status_code, 200)
        profiles = UserProfile.objects.filter(email=email)
        eq_(len(profiles), 1)
        eq_(profiles[0].username, 'newuser')
        eq_(profiles[0].display_name, 'newuser')

    @patch('requests.post')
    @patch('mkt.users.views.record_action')
    def test_browserid_misplaced_auth_user(self, record_action, http_request):
        """
        Login still works even after the user has changed his email
        address on AMO.
        """
        url = reverse('users.browserid_login')
        profile = UserProfile.objects.create(username='login_test',
                                             email='bob@example.com')
        profile.email = 'charlie@example.com'
        profile.save()
        http_request.return_value = FakeResponse(
            200,
            {'status': 'okay', 'email': 'charlie@example.com'})
        res = self.client.post(url, data=dict(assertion='fake-assertion',
                                              audience='fakeamo.org'))
        eq_(res.status_code, 200)

    @patch('requests.post')
    @patch('mkt.users.views.record_action')
    def test_browserid_no_auth_user(self, record_action, http_request):
        """
        Login still works after a new UserProfile has been created for an
        email address another UserProfile formerly used.
        """
        url = reverse('users.browserid_login')
        UserProfile.objects.get(email="jbalogh@mozilla.com").update(
            email="badnews@example.com")
        UserProfile.objects.create(email="jbalogh@mozilla.com")
        http_request.return_value = FakeResponse(
            200, {'status': 'okay', 'email': 'jbalogh@mozilla.com'})
        res = self.client.post(url, data=dict(assertion='fake-assertion',
                                              audience='fakeamo.org'))
        eq_(res.status_code, 200)

    @patch('requests.post')
    @patch('mkt.users.views.record_action')
    def test_browserid_no_mark_as_market(self, record_action, post):
        email = 'newuser@example.com'
        self._browserid_login(email, post)
        profile = UserProfile.objects.get(email=email)
        assert not profile.notes

    @patch('requests.post')
    def test_browserid_login_failure(self, http_request):
        """
        A failure response from BrowserID results in login failure.
        """
        http_request.return_value = FakeResponse(
            200, {'status': 'busted'})
        res = self.client.post(reverse('users.browserid_login'),
                               data=dict(assertion='fake-assertion',
                                         audience='fakeamo.org'))
        eq_(res.status_code, 401)
        assert 'Persona authentication failure' in res.content

    @patch('requests.post')
    @patch('mkt.users.views.record_action')
    def test_browserid_duplicate_username(self, record_action, post):
        email = 'jbalogh@example.com'  # existing
        post.return_value = FakeResponse(
            200, {'status': 'okay', 'email': email})
        res = self.client.post(reverse('users.browserid_login'),
                               data=dict(assertion='fake-assertion',
                                         audience='fakeamo.org'))
        eq_(res.status_code, 200)
        profiles = UserProfile.objects.filter(email=email)
        eq_(profiles[0].username, 'jbalogh2')
        eq_(profiles[0].display_name, 'jbalogh2')
        # Note: lower level unit tests for this functionality are in
        # TestAutoCreateUsername()

    @patch('requests.post')
    def create_profile(self, http_request):
        email = 'user@example.com'
        http_request.return_value = FakeResponse(
            200, {'status': 'okay', 'email': email})
        request = fake_request()
        browserid_authenticate(request=request, assertion='fake-assertion')
        return UserProfile.objects.get(email=email)

    @patch('mkt.users.views.record_action')
    def test_mmo_source(self, record_action):
        profile = self.create_profile()
        eq_(profile.source, amo.LOGIN_SOURCE_MMO_BROWSERID)
        assert record_action.called

    @patch.object(settings, 'NATIVE_BROWSERID_VERIFICATION_URL',
                  'http://my-custom-b2g-verifier.org/verify')
    @patch.object(settings, 'SITE_URL', 'http://testserver')
    @patch.object(settings, 'UNVERIFIED_ISSUER', 'some-issuer')
    @patch('requests.post')
    def test_mobile_persona_login(self, http_request):
        http_request.return_value = FakeResponse(
            200, {'status': 'okay', 'email': 'jbalogh@mozilla.com'})
        self.client.post(reverse('users.browserid_login'),
                         data=dict(assertion='fake-assertion',
                                   audience='fakeamo.org',
                                   is_mobile='1'))
        http_request.assert_called_with(
            settings.NATIVE_BROWSERID_VERIFICATION_URL,
            data=ANY, timeout=ANY)
        data = http_request.call_args[1]['data']
        eq_(data['audience'], 'http://testserver')
        eq_(data['experimental_forceIssuer'], settings.UNVERIFIED_ISSUER)
        eq_(data['experimental_allowUnverified'], 'true')

    @patch.object(settings, 'SITE_URL', 'http://testserver')
    @patch.object(settings, 'UNVERIFIED_ISSUER', 'some-issuer')
    @patch('requests.post')
    def test_non_mobile_persona_login(self, http_request):
        http_request.return_value = FakeResponse(
            200, {'status': 'okay', 'email': 'jbalogh@mozilla.com'})
        self.client.post(reverse('users.browserid_login'),
                         data=dict(assertion='fake-assertion',
                                   audience='fakeamo.org'))
        assert http_request.called
        data = http_request.call_args[1]['data']
        eq_(data['audience'], 'http://testserver')
        eq_(data['experimental_forceIssuer'], settings.UNVERIFIED_ISSUER)
        assert 'experimental_allowUnverified' not in data, (
                'not allowing unverfied when not native')

    @patch.object(settings, 'NATIVE_BROWSERID_VERIFICATION_URL',
                  'http://my-custom-b2g-verifier.org/verify')
    @patch.object(settings, 'SITE_URL', 'http://testserver')
    @patch.object(settings, 'UNVERIFIED_ISSUER', None)
    @patch('requests.post')
    def test_mobile_persona_login_without_issuer(self, http_request):
        http_request.return_value = FakeResponse(
            200, {'status': 'okay', 'email': 'jbalogh@mozilla.com'})
        self.client.post(reverse('users.browserid_login'),
                         data=dict(assertion='fake-assertion',
                                   audience='fakeamo.org',
                                   is_mobile='1'))
        data = http_request.call_args[1]['data']
        eq_(data['audience'], 'http://testserver')
        assert 'experimental_forceIssuer' not in data, (
                'not forcing issuer when the setting is blank')

    @patch('requests.post')
    def test_mobile_persona_login_ignores_garbage(self, http_request):
        http_request.return_value = FakeResponse(
            200, {'status': 'okay', 'email': 'jbalogh@mozilla.com'})
        self.client.post(reverse('users.browserid_login'),
                         data=dict(assertion='fake-assertion',
                                   audience='fakeamo.org',
                                   is_mobile='<garbage>'))
