from nose.tools import ok_
from rest_framework.generics import GenericAPIView

from django.contrib.auth.models import AnonymousUser
from django.test.client import RequestFactory

from mkt.access.middleware import ACLMiddleware
from mkt.operators.models import OperatorPermission
from mkt.operators.permissions import IsOperatorPermission
from mkt.site.fixtures import fixture
from mkt.site.tests import TestCase
from mkt.users.models import UserProfile


class TestIsOperatorPermission(TestCase):
    fixtures = fixture('user_2519')

    def setUp(self):
        super(TestIsOperatorPermission, self).setUp()
        self.auth = IsOperatorPermission()
        self.user = UserProfile.objects.get(pk=2519)
        self.profile = self.user
        self.view = GenericAPIView()

    def is_authorized(self, anon=False):
        request = RequestFactory().get('/')
        request.user = AnonymousUser() if anon else self.user
        ACLMiddleware().process_request(request)
        return self.auth.has_permission(request, self.view)

    def test_anon(self):
        ok_(not self.is_authorized(anon=True))

    def test_auth_no_perm(self):
        ok_(not self.is_authorized())

    def test_auth_with_perm(self):
        OperatorPermission.objects.create(user=self.profile, region=1,
                                          carrier=8)
        ok_(self.is_authorized())
