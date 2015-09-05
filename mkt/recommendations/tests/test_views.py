import json

from django.core.urlresolvers import reverse
from django.test.utils import override_settings

import requests
from mock import patch
from nose.tools import eq_, ok_
from requests.exceptions import RequestException, Timeout

import mkt
from mkt.api.tests.test_oauth import RestOAuth
from mkt.site.fixtures import fixture
from mkt.site.tests import app_factory, ESTestCase
from mkt.webapps.models import Webapp


class Response(requests.Response):
    def __init__(self, status_code, content=None):
        super(Response, self).__init__()
        self.status_code = status_code
        self._content = content


class TestRecommendationView(RestOAuth, ESTestCase):
    fixtures = fixture('user_2519')

    def setUp(self):
        super(TestRecommendationView, self).setUp()
        self.url = reverse('api-v2:apps-recommend')

        self.requests_patcher = patch('mkt.recommendations.views.requests')
        self.patched_requests = self.requests_patcher.start()
        self.patched_requests.patcher = self.requests_patcher
        self.addCleanup(self.requests_patcher.stop)

    def test_list_anonymous(self):
        "Test anonymous results in a popular search."
        res = self.anon.get(self.url)
        assert not self.patched_requests.called
        eq_(res.status_code, 200)

    def test_list_recommendations_disabled(self):
        with self.settings(RECOMMENDATIONS_ENABLED=False):
            res = self.client.get(self.url)
            assert not self.patched_requests.get.called
            eq_(res.status_code, 200)

    def test_recommendation_api_4xx(self):
        "Test a non-200 returns the popular list."
        with self.settings(RECOMMENDATIONS_API_URL='http://hy.fr',
                           RECOMMENDATIONS_ENABLED=True):
            self.patched_requests.get.return_value = Response(404)
            res = self.client.get(self.url)
            eq_(res.status_code, 200)

    def test_recommendation_api_5xx(self):
        "Test a non-200 returns the popular list."
        with self.settings(RECOMMENDATIONS_API_URL='http://hy.fr',
                           RECOMMENDATIONS_ENABLED=True):
            self.patched_requests.get.side_effect = RequestException('500')
            res = self.client.get(self.url)
            eq_(res.status_code, 200)

    def test_recommendation_api_timeout(self):
        "Test a non-200 returns the popular list."
        with self.settings(RECOMMENDATIONS_API_URL='http://hy.fr',
                           RECOMMENDATIONS_ENABLED=True):
            self.patched_requests.get.side_effect = Timeout
            res = self.client.get(self.url)
            eq_(res.status_code, 200)

    @patch('mkt.recommendations.views.statsd')
    def test_recommendation_statsd(self, statsd):
        with self.settings(RECOMMENDATIONS_API_URL='http://hy.fr',
                           RECOMMENDATIONS_ENABLED=True):
            self.client.get(self.url)
            assert statsd.timer.called


@override_settings(RECOMMENDATIONS_API_URL='http://hy.fr',
                   RECOMMENDATIONS_ENABLED=True)
class TestRecommendationViewMocked(RestOAuth, ESTestCase):
    """
    This test creates 2 apps and mocks the recommenation API to always return
    those two apps.

    See `TestRecommendationView` for tests that don't need this mocking.

    """
    fixtures = fixture('user_2519')

    def setUp(self):
        super(TestRecommendationViewMocked, self).setUp()
        self.url = reverse('api-v2:apps-recommend')

        self.requests_patcher = patch('mkt.recommendations.views.requests')
        self.patched_requests = self.requests_patcher.start()
        self.patched_requests.patcher = self.requests_patcher
        self.addCleanup(self.requests_patcher.stop)

        self.apps = [app_factory() for i in range(2)]
        resp_value = json.dumps({
            'user': self.profile.recommendation_hash,
            'recommendations': [a.pk for a in self.apps],
        })
        self.patched_requests.get.return_value = Response(200, resp_value)
        self.refresh('webapp')

    def test_list_recommendations_enabled(self):
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        assert self.patched_requests.get.called
        eq_(self.patched_requests.get.call_args[0][0],
            'http://hy.fr/api/v2/recommend/20/{user_hash}/'.format(
                user_hash=self.profile.recommendation_hash))
        objects = res.json['objects']
        eq_(len(objects), 2)
        self.assertSetEqual([a['id'] for a in objects],
                            [a.pk for a in self.apps])
        # Light check for a full app object in response.
        for k in ('description', 'manifest_url', 'name', 'slug'):
            ok_(k in objects[0], 'Key %s not found in response' % k)

    def test_filter_by_device(self):
        self.apps[0].webappdevicetype_set.create(
            device_type=mkt.DEVICE_GAIA.id)
        self.reindex(Webapp)

        res = self.client.get(self.url, {'dev': mkt.DEVICE_GAIA.api_name})
        eq_(res.status_code, 200)
        objects = res.json['objects']
        eq_(len(objects), 1)
        self.assertSetEqual([a['id'] for a in objects], [self.apps[0].pk])

    def test_filter_by_desktop(self):
        self.apps[0].webappdevicetype_set.create(
            device_type=mkt.DEVICE_DESKTOP.id)
        self.reindex(Webapp)

        res = self.client.get(self.url, {'dev': mkt.DEVICE_DESKTOP.api_name})
        eq_(res.status_code, 200)
        objects = res.json['objects']
        eq_(len(objects), 1)
        self.assertSetEqual([a['id'] for a in objects], [self.apps[0].pk])

    def test_no_filter_if_no_dev(self):
        self.apps[0].webappdevicetype_set.create(
            device_type=mkt.DEVICE_GAIA.id)
        self.reindex(Webapp)

        res = self.client.get(self.url, {'dev': ''})
        eq_(res.status_code, 200)
        objects = res.json['objects']
        eq_(len(objects), 2)
        self.assertSetEqual([a['id'] for a in objects],
                            [a.pk for a in self.apps])

    def test_no_installed_apps(self):
        self.profile.installed_set.create(webapp=self.apps[0])

        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        objects = res.json['objects']
        eq_(len(objects), 1)
        self.assertSetEqual([a['id'] for a in objects], [self.apps[1].pk])
