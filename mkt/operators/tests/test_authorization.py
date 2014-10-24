from nose.tools import ok_
from rest_framework.generics import GenericAPIView

from django.contrib.auth.models import AnonymousUser
from django.test.client import RequestFactory

from amo.tests import TestCase
from mkt.access.middleware import ACLMiddleware
from mkt.carriers import CARRIER_MAP as CARRIERS
from mkt.feed.constants import FEED_TYPE_SHELF
from mkt.feed.tests.test_models import FeedTestMixin
from mkt.operators.authorization import (OperatorAuthorization,
                                         OperatorShelfAuthorization)
from mkt.operators.models import OperatorPermission
from mkt.regions import REGIONS_DICT as REGIONS
from mkt.site.fixtures import fixture
from mkt.users.models import UserProfile


class BaseTestOperatorAuthorization(FeedTestMixin, TestCase):
    fixtures = fixture('user_2519') + FeedTestMixin.fixtures

    def setUp(self):
        super(BaseTestOperatorAuthorization, self).setUp()
        self.auth = self.auth_class()
        self.user = UserProfile.objects.get(pk=2519)
        self.view = GenericAPIView()

    def make_admin(self):
        self.grant_permission(self.user, 'OperatorDashboard:*')

    def give_objpermission(self, carrier, region):
        carrier_id = CARRIERS[carrier].id
        region_id = REGIONS[region].id
        OperatorPermission.objects.create(user=self.user, region=region_id,
                                          carrier=carrier_id)

    def is_authorized(self, verb, anon=False, carrier='telefonica',
                      region='br'):
        request = self.request(verb, anon=anon, carrier=carrier,
                               region=region)
        return self.auth.has_permission(request, self.view)

    def is_object_authorized(self, verb, obj, anon=False, carrier='telefonica',
                             region='br'):
        request = self.request(verb, anon=anon, carrier=carrier,
                               region=region)
        return self.auth.has_object_permission(request, self.view, obj)

    def request(self, verb, anon=False, **kwargs):
        request = getattr(RequestFactory(), verb.lower())('/', kwargs)
        request.user = AnonymousUser() if anon else self.user
        ACLMiddleware().process_request(request)
        return request


class TestOperatorAuthorization(BaseTestOperatorAuthorization):
    auth_class = OperatorAuthorization

    def test_safe(self):
        ok_(self.is_authorized('GET', anon=True))
        ok_(self.is_authorized('GET'))

    def test_safe_permission(self):
        self.make_admin()
        ok_(self.is_authorized('GET'))

    def test_safe_objpermission_correct(self):
        self.give_objpermission('telefonica', 'br')
        ok_(self.is_authorized('GET', carrier='telefonica', region='br'))

    def test_safe_objpermission_mismatch(self):
        self.give_objpermission('telefonica', 'br')
        ok_(self.is_authorized('GET', carrier='america_movil', region='fr'))

    def test_unsafe(self):
        ok_(not self.is_authorized('POST', anon=True))
        ok_(not self.is_authorized('POST'))

    def test_unsafe_permission(self):
        self.make_admin()
        ok_(self.is_authorized('POST'))

    def test_unsafe_objpermission_correct(self):
        self.give_objpermission('telefonica', 'br')
        ok_(self.is_authorized('POST'))

    def test_unsafe_objpermission_mismatch(self):
        self.give_objpermission('telefonica', 'br')
        ok_(not self.is_authorized('POST', carrier='america_movil',
                                   region='fr'))


class TestOperatorShelfAuthorization(BaseTestOperatorAuthorization):
    auth_class = OperatorShelfAuthorization

    def setUp(self):
        super(TestOperatorShelfAuthorization, self).setUp()
        self.feed_item = self.feed_item_factory(carrier=1, region=7,  # TEF/BR
                                                item_type=FEED_TYPE_SHELF)
        self.shelf = self.feed_item.shelf

    def test_safe_object(self):
        ok_(self.is_object_authorized('GET', self.feed_item, anon=True))
        ok_(self.is_object_authorized('GET', self.shelf, anon=True))

        ok_(self.is_object_authorized('GET', self.feed_item))
        ok_(self.is_object_authorized('GET', self.shelf))

        self.make_admin()
        ok_(self.is_object_authorized('GET', self.feed_item))
        ok_(self.is_object_authorized('GET', self.shelf))

    def test_safe_object_objpermission_correct(self):
        self.give_objpermission('telefonica', 'br')
        ok_(self.is_object_authorized('GET', self.feed_item))
        ok_(self.is_object_authorized('GET', self.shelf))

    def test_safe_object_objpermission_mismatch(self):
        self.give_objpermission('america_movil', 'fr')
        ok_(self.is_object_authorized('GET', self.feed_item))
        ok_(self.is_object_authorized('GET', self.shelf))

    def test_unsafe_object(self):
        ok_(not self.is_object_authorized('POST', self.feed_item, anon=True))
        ok_(not self.is_object_authorized('POST', self.shelf, anon=True))

        ok_(not self.is_object_authorized('POST', self.feed_item))
        ok_(not self.is_object_authorized('POST', self.shelf))

        self.make_admin()
        ok_(self.is_object_authorized('POST', self.feed_item))
        ok_(self.is_object_authorized('POST', self.shelf))

    def test_unsafe_object_objpermission_correct(self):
        self.give_objpermission('telefonica', 'br')
        ok_(self.is_object_authorized('POST', self.feed_item))
        ok_(self.is_object_authorized('POST', self.shelf))

    def test_unsafe_object_objpermission_mismatch(self):
        self.give_objpermission('america_movil', 'fr')
        ok_(not self.is_object_authorized('POST', self.feed_item))
        ok_(not self.is_object_authorized('POST', self.shelf))
