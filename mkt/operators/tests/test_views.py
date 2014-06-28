from django.core.urlresolvers import reverse

from nose.tools import eq_
from pyquery import PyQuery as pq

import amo
import amo.tests
from amo.tests import app_factory
from mkt.developers.models import PreloadTestPlan
from mkt.operators.views import preloads
from mkt.site.fixtures import fixture
from mkt.users.models import UserProfile


class TestPreloadCandidates(amo.tests.TestCase):
    fixtures = fixture('user_operator')

    def setUp(self):
        self.create_switch('preload-apps')
        self.url = reverse('operators.preloads')
        self.user = UserProfile.objects.get()
        self.app = app_factory()

    def _preload_factory(self):
        return PreloadTestPlan.objects.create(addon=app_factory(),
                                              filename='tstpn')

    def test_preloads(self):
        plan = self._preload_factory()
        req = amo.tests.req_factory_factory(self.url, user=self.user)
        res = preloads(req)
        eq_(res.status_code, 200)
        doc = pq(res.content)

        eq_(doc('tbody tr').length, 1)
        eq_(doc('td:last-child a').attr('href'),
            plan.preload_test_plan_url)
