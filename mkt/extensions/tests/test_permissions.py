from django.contrib.auth.models import AnonymousUser
from django.test.client import RequestFactory

from mock import Mock
from nose.tools import eq_

from mkt.extensions.models import Extension
from mkt.extensions.permissions import (AllowExtensionReviewerReadOnly,
                                        AllowOwnerButReadOnlyIfBlocked)
from mkt.site.fixtures import fixture
from mkt.site.tests import TestCase
from mkt.users.models import UserProfile


class TestAllowExtensionReviewerReadOnly(TestCase):
    fixtures = fixture('user_2519')

    def setUp(self):
        self.permission = AllowExtensionReviewerReadOnly()
        self.user = AnonymousUser()
        self.request_factory = RequestFactory()

        self.unsafe_methods = ('patch', 'post', 'put', 'delete')
        self.safe_methods = ('get', 'options', 'head')

    def _request(self, verb):
        request = getattr(self.request_factory, verb)('/')
        request.user = self.user
        if self.user.is_authenticated():
            request.groups = request.user.groups.all()
        return request

    def test_has_permission_anonymous(self):
        for verb in self.safe_methods + self.unsafe_methods:
            eq_(self.permission.has_permission(self._request(verb), 'myview'),
                False)

    def test_has_permission_no_rights(self):
        self.user = UserProfile.objects.get(pk=2519)
        for verb in self.safe_methods + self.unsafe_methods:
            eq_(self.permission.has_permission(self._request(verb), 'myview'),
                False)

    def test_has_permission_reviewer(self):
        self.user = UserProfile.objects.get(pk=2519)
        self.grant_permission(self.user, 'ContentTools:AddonReview')
        for verb in self.safe_methods:
            eq_(self.permission.has_permission(self._request(verb), 'myview'),
                True)
        # Unsafe methods are still disallowed.
        for verb in self.unsafe_methods:
            eq_(self.permission.has_permission(self._request(verb), 'myview'),
                False)

    def test_has_object_permission(self):
        obj = Mock()

        for verb in self.safe_methods + self.unsafe_methods:
            eq_(self.permission.has_object_permission(self._request(verb),
                'myview', obj), False)

    def test_has_object_permission_no_rights(self):
        self.user = UserProfile.objects.get(pk=2519)
        obj = Mock()

        for verb in self.safe_methods + self.unsafe_methods:
            eq_(self.permission.has_object_permission(self._request(verb),
                'myview', obj), False)

    def test_has_object_permission_reviewer(self):
        self.user = UserProfile.objects.get(pk=2519)
        self.grant_permission(self.user, 'ContentTools:AddonReview')
        obj = Mock()

        for verb in self.safe_methods:
            eq_(self.permission.has_object_permission(self._request(verb),
                'myview', obj), True)

        # Unsafe methods are still disallowed.
        for verb in self.unsafe_methods:
            eq_(self.permission.has_object_permission(self._request(verb),
                'myview', obj), False)


class TestAllowOwnerIfNotBlocked(TestCase):
    fixtures = fixture('user_2519')

    def setUp(self):
        self.permission = AllowOwnerButReadOnlyIfBlocked()
        self.user = AnonymousUser()
        self.request_factory = RequestFactory()
        self.extension = Extension.objects.create()

        self.unsafe_methods = ('patch', 'post', 'put', 'delete')
        self.safe_methods = ('get', 'options', 'head')

    def _request(self, verb):
        request = getattr(self.request_factory, verb)('/')
        request.user = self.user
        return request

    def test_has_permission_anonymous(self):
        eq_(self.permission.has_permission(self._request('get'), 'myview'),
            False)

    def test_has_permission_logged_in(self):
        self.user = UserProfile.objects.get(pk=2519)
        eq_(self.permission.has_permission(self._request('get'), 'myview'),
            True)

    def test_has_object_permission_not_author(self):
        obj = self.extension
        eq_(self.permission.has_object_permission(
            self._request('get'), 'myview', obj), False)
        self.user = UserProfile.objects.get(pk=2519)
        eq_(self.permission.has_object_permission(
            self._request('get'), 'myview', obj), False)

    def test_has_object_permission_author(self):
        obj = self.extension
        self.user = UserProfile.objects.get(pk=2519)
        obj.authors.add(self.user)
        for verb in self.safe_methods + self.unsafe_methods:
            eq_(self.permission.has_object_permission(
                self._request(verb), 'myview', obj), True)

    def test_has_object_permission_blocked(self):
        obj = self.extension
        self.user = UserProfile.objects.get(pk=2519)
        obj.authors.add(self.user)
        obj.block()
        for verb in self.safe_methods:
            eq_(self.permission.has_object_permission(
                self._request(verb), 'myview', obj), True)
        for verb in self.unsafe_methods:
            eq_(self.permission.has_object_permission(
                self._request(verb), 'myview', obj), False)
