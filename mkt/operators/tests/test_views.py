import json

from django.core.urlresolvers import reverse

from nose.tools import eq_
from pyquery import PyQuery as pq

import mkt
import mkt.site.tests
from mkt.api.tests.test_oauth import RestOAuth
from mkt.developers.models import PreloadTestPlan
from mkt.operators.models import OperatorPermission
from mkt.operators.views import preloads
from mkt.site.fixtures import fixture
from mkt.site.tests import app_factory
from mkt.users.models import UserProfile


class TestPreloadCandidates(mkt.site.tests.TestCase):
    fixtures = fixture('user_operator')

    def setUp(self):
        self.create_switch('preload-apps')
        self.url = reverse('operators.preloads')
        self.user = UserProfile.objects.get(pk=322)
        self.app = app_factory()

    def _preload_factory(self):
        return PreloadTestPlan.objects.create(webapp=app_factory(),
                                              filename='tstpn')

    def test_preloads(self):
        plan = self._preload_factory()
        req = mkt.site.tests.req_factory_factory(self.url, user=self.user)
        res = preloads(req)
        eq_(res.status_code, 200)
        doc = pq(res.content)

        eq_(doc('tbody tr').length, 1)
        eq_(doc('td:last-child a').attr('href'),
            plan.preload_test_plan_url)


class TestOperatorPermissionsViewSet(RestOAuth, mkt.site.tests.ESTestCase):
    fixtures = RestOAuth.fixtures + fixture('user_999')

    def setUp(self):
        super(TestOperatorPermissionsViewSet, self).setUp()
        self.other_user = UserProfile.objects.get(id=999)
        self.url = reverse('api-v2:operator-permissions')

    def create(self, carrier, region, user):
        return OperatorPermission.objects.create(
            carrier=carrier.id, region=region.id, user=user)

    def get(self, client):
        res = client.get(self.url)
        data = json.loads(res.content)
        eq_(res.status_code, 200)
        return res, data

    def test_anonymous(self):
        res, data = self.get(self.anon)
        eq_(data['meta']['total_count'], 0)

    def test_authenticated_empty(self):
        res, data = self.get(self.client)
        eq_(data['meta']['total_count'], 0)

    def test_authenticated_single(self):
        self.create(mkt.carriers.TELEFONICA, mkt.regions.BRA, self.user)
        res, data = self.get(self.client)
        eq_(data['meta']['total_count'], 1)
        eq_(data['objects'][0]['carrier'], mkt.carriers.TELEFONICA.slug)
        eq_(data['objects'][0]['region'], mkt.regions.BRA.slug)

    def test_authenticated_multiple(self):
        regions = (mkt.regions.BRA, mkt.regions.FRA)
        for region in regions:
            self.create(mkt.carriers.TELEFONICA, region, self.user)
        res, data = self.get(self.client)
        eq_(data['meta']['total_count'], len(regions))

    def test_authenticated_other_people(self):
        self.create(mkt.carriers.TELEFONICA, mkt.regions.BRA, self.other_user)
        res, data = self.get(self.client)
        eq_(data['meta']['total_count'], 0)

    def test_admin(self):
        self.grant_permission(self.user, 'OperatorDashboard:*')
        res, data = self.get(self.client)
        eq_(res.status_code, 200)
        eq_(data, ['*'])
