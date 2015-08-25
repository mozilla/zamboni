from nose.tools import ok_
from rest_framework.generics import GenericAPIView

from django.contrib.auth.models import AnonymousUser
from django.test.client import RequestFactory

from mkt.access.middleware import ACLMiddleware
from mkt.feed.permissions import FeedPermission
from mkt.site.fixtures import fixture
from mkt.site.tests import TestCase
from mkt.users.models import UserProfile


class TestFeedPermission(TestCase):
    auth_class = FeedPermission
    fixtures = fixture('user_2519')

    def setUp(self):
        super(TestFeedPermission, self).setUp()
        self.auth = self.auth_class()
        self.user = UserProfile.objects.get(pk=2519)
        self.profile = self.user
        self.view = GenericAPIView()

    def give_permission(self):
        self.grant_permission(self.profile, 'Feed:Curate')

    def request(self, verb, anon=False):
        request = getattr(RequestFactory(), verb.lower())('/')
        request.user = AnonymousUser() if anon else self.user
        ACLMiddleware().process_request(request)
        return request

    def is_authorized(self, request):
        return self.auth.has_permission(request, self.view)

    def test_get(self):
        ok_(self.is_authorized(self.request('GET', anon=True)))
        ok_(self.is_authorized(self.request('GET')))

    def test_get_permission(self):
        self.give_permission()
        ok_(self.is_authorized(self.request('GET')))

    def test_head(self):
        ok_(self.is_authorized(self.request('HEAD', anon=True)))
        ok_(self.is_authorized(self.request('HEAD')))

    def test_head_permission(self):
        self.give_permission()
        ok_(self.is_authorized(self.request('HEAD')))

    def test_options(self):
        ok_(self.is_authorized(self.request('OPTIONS', anon=True)))
        ok_(self.is_authorized(self.request('OPTIONS')))

    def test_options_permission(self):
        self.give_permission()
        ok_(self.is_authorized(self.request('OPTIONS')))

    def test_post(self):
        ok_(not self.is_authorized(self.request('POST', anon=True)))
        ok_(not self.is_authorized(self.request('POST')))

    def test_post_permission(self):
        self.give_permission()
        ok_(self.is_authorized(self.request('POST')))

    def test_patch(self):
        ok_(not self.is_authorized(self.request('PATCH', anon=True)))
        ok_(not self.is_authorized(self.request('PATCH')))

    def test_patch_permission(self):
        self.give_permission()
        ok_(self.is_authorized(self.request('PATCH')))

    def test_put(self):
        ok_(not self.is_authorized(self.request('PUT', anon=True)))
        ok_(not self.is_authorized(self.request('PUT')))

    def test_put_permission(self):
        self.give_permission()
        ok_(self.is_authorized(self.request('PUT')))

    def test_delete(self):
        ok_(not self.is_authorized(self.request('DELETE', anon=True)))
        ok_(not self.is_authorized(self.request('DELETE')))

    def test_delete_permission(self):
        self.give_permission()
        ok_(self.is_authorized(self.request('DELETE')))
