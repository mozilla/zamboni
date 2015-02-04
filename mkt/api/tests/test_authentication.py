from datetime import datetime

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.test.client import RequestFactory

from mock import Mock, patch
from multidb.pinning import this_thread_is_pinned, unpin_this_thread
from nose.tools import eq_, ok_
from rest_framework.request import Request

from mkt.access.models import Group, GroupUser
from mkt.api import authentication
from mkt.api.middleware import (APIBaseMiddleware, RestOAuthMiddleware,
                                RestSharedSecretMiddleware)
from mkt.api.models import Access
from mkt.api.tests.test_oauth import OAuthClient
from mkt.site.fixtures import fixture
from mkt.site.helpers import absolutify
from mkt.site.tests import TestCase
from mkt.users.models import UserProfile


class TestRestOAuthAuthentication(TestCase):
    fixtures = fixture('user_2519', 'group_admin', 'group_editor')

    def setUp(self):
        self.api_name = 'foo'
        self.profile = UserProfile.objects.get(pk=2519)
        self.profile.update(read_dev_agreement=datetime.today())
        self.access = Access.objects.create(key='test_oauth_key',
                                            secret='super secret',
                                            user=self.profile)
        self.auth = authentication.RestOAuthAuthentication()
        self.middlewares = [APIBaseMiddleware, RestOAuthMiddleware]
        unpin_this_thread()

    def call(self, client=None):
        client = client or OAuthClient(self.access)
        # Make a fake POST somewhere. We use POST in order to properly test db
        # pinning after auth.
        url = absolutify('/api/whatever')
        req = RequestFactory().post(
            url, HTTP_HOST='testserver',
            HTTP_AUTHORIZATION=client.sign('POST', url)[1]['Authorization'])
        req.user = AnonymousUser()
        for m in self.middlewares:
            m().process_request(req)
        return req

    def add_group_user(self, user, *names):
        for name in names:
            group = Group.objects.get(name=name)
            GroupUser.objects.create(user=self.profile, group=group)

    def test_accepted(self):
        req = Request(self.call())
        eq_(self.auth.authenticate(req), (self.profile, None))

    def test_request_token_fake(self):
        c = Mock()
        c.key = self.access.key
        c.secret = 'mom'
        ok_(not self.auth.authenticate(
            Request(self.call(client=OAuthClient(c)))))
        ok_(not this_thread_is_pinned())

    def test_request_admin(self):
        self.add_group_user(self.profile, 'Admins')
        ok_(not self.auth.authenticate(Request(self.call())))

    def test_request_has_role(self):
        self.add_group_user(self.profile, 'App Reviewers')
        ok_(self.auth.authenticate(Request(self.call())))


class TestRestAnonymousAuthentication(TestCase):

    def setUp(self):
        self.auth = authentication.RestAnonymousAuthentication()
        self.request = RequestFactory().post('/api/whatever')
        unpin_this_thread()

    def test_auth(self):
        user, token = self.auth.authenticate(self.request)
        ok_(isinstance(user, AnonymousUser))
        eq_(token, None)
        ok_(not this_thread_is_pinned())


@patch.object(settings, 'SECRET_KEY', 'gubbish')
class TestSharedSecretAuthentication(TestCase):
    fixtures = fixture('user_2519')

    def setUp(self):
        self.auth = authentication.RestSharedSecretAuthentication()
        self.profile = UserProfile.objects.get(pk=2519)
        self.profile.update(email=self.profile.email)
        self.middlewares = [APIBaseMiddleware,
                            RestSharedSecretMiddleware]
        unpin_this_thread()

    def test_session_auth_query(self):
        req = RequestFactory().post(
            '/api/?_user=cfinke@m.com,56b6f1a3dd735d962c56ce7d8f46e02ec1d4748d'
            '2c00c407d75f0969d08bb9c68c31b3371aa8130317815c89e5072e31bb94b4121'
            'c5c165f3515838d4d6c60c4,165d631d3c3045458b4516242dad7ae')
        req.user = AnonymousUser()
        for m in self.middlewares:
            m().process_request(req)
        ok_(self.auth.authenticate(Request(req)))
        ok_(req.user.is_authenticated())
        eq_(self.profile.pk, req.user.pk)

    def test_failed_session_auth_query(self):
        req = RequestFactory().post('/api/?_user=bogus')
        req.user = AnonymousUser()
        for m in self.middlewares:
            m().process_request(req)
        ok_(not self.auth.authenticate(Request(req)))
        ok_(not req.user.is_authenticated())

    def test_session_auth(self):
        req = RequestFactory().post(
            '/api/',
            HTTP_AUTHORIZATION='mkt-shared-secret '
            'cfinke@m.com,56b6f1a3dd735d962c56'
            'ce7d8f46e02ec1d4748d2c00c407d75f0969d08bb'
            '9c68c31b3371aa8130317815c89e5072e31bb94b4'
            '121c5c165f3515838d4d6c60c4,165d631d3c3045'
            '458b4516242dad7ae')
        req.user = AnonymousUser()
        for m in self.middlewares:
            m().process_request(req)
        ok_(self.auth.authenticate(Request(req)))
        ok_(req.user.is_authenticated())
        eq_(self.profile.pk, req.user.pk)

    def test_failed_session_auth(self):
        req = RequestFactory().post(
            '/api/',
            HTTP_AUTHORIZATION='mkt-shared-secret bogus')
        req.user = AnonymousUser()
        for m in self.middlewares:
            m().process_request(req)
        ok_(not self.auth.authenticate(Request(req)))
        ok_(not req.user.is_authenticated())

    def test_session_auth_no_post(self):
        req = RequestFactory().post('/api/')
        req.user = AnonymousUser()
        for m in self.middlewares:
            m().process_request(req)
        ok_(not self.auth.authenticate(Request(req)))
        ok_(not req.user.is_authenticated())


@patch.object(settings, 'SECRET_KEY', 'gubbish')
class TestMultipleAuthenticationDRF(TestCase):
    fixtures = fixture('user_2519')

    def setUp(self):
        self.profile = UserProfile.objects.get(pk=2519)

    def test_multiple_shared_works(self):
        request = RequestFactory().post(
            '/api',
            HTTP_AUTHORIZATION='mkt-shared-secret '
            'cfinke@m.com,56b6f1a3dd735d962c56'
            'ce7d8f46e02ec1d4748d2c00c407d75f0969d08bb'
            '9c68c31b3371aa8130317815c89e5072e31bb94b4'
            '121c5c165f3515838d4d6c60c4,165d631d3c3045'
            '458b4516242dad7ae')
        request.user = AnonymousUser()
        drf_request = Request(request)

        # Start with an AnonymousUser on the request, because that's a classic
        # situation: we already went through a middleware, it didn't find a
        # session cookie, if set request.user = AnonymousUser(), and now we
        # are going through the authentication code in the API.
        request.user = AnonymousUser()

        # Call middleware as they would normally be called.
        APIBaseMiddleware().process_request(request)
        RestSharedSecretMiddleware().process_request(request)
        RestOAuthMiddleware().process_request(request)

        drf_request.authenticators = (
            authentication.RestSharedSecretAuthentication(),
            authentication.RestOAuthAuthentication())

        eq_(drf_request.user, self.profile)
        eq_(drf_request._request.user, self.profile)
        eq_(drf_request.user.is_authenticated(), True)
        eq_(drf_request._request.user.is_authenticated(), True)
        eq_(drf_request.user.pk, self.profile.pk)
        eq_(drf_request._request.user.pk, self.profile.pk)

    def test_multiple_fail(self):
        request = RequestFactory().post('/api')
        request.user = AnonymousUser()
        drf_request = Request(request)
        request.user = AnonymousUser()
        drf_request.authenticators = (
            authentication.RestSharedSecretAuthentication(),
            authentication.RestOAuthAuthentication())

        eq_(drf_request.user.is_authenticated(), False)
        eq_(drf_request._request.user.is_authenticated(), False)
