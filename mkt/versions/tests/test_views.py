import json

from django.core.urlresolvers import reverse

from nose.tools import eq_, ok_
from rest_framework.reverse import reverse as rest_reverse

from test_utils import RequestFactory

import amo
from amo.tests import app_factory
from mkt.api.base import get_url
from mkt.api.tests.test_oauth import RestOAuth
from mkt.site.fixtures import fixture
from mkt.versions.models import Version


class TestVersionViewSet(RestOAuth):
    fixtures = fixture('user_2519')

    def setUp(self):
        self.app = app_factory()
        self.app_url = get_url('app', self.app.pk)
        self.version = self.app.current_version
        self.request = RequestFactory()
        super(TestVersionViewSet, self).setUp()

    def test_has_cors(self):
        url = rest_reverse('version-detail', kwargs={'pk': self.version.pk})
        self.assertCORS(self.client.get(url), 'get', 'put', 'patch')

    def test_get(self, version=None, **kwargs):
        if not version:
            version = self.version

        url = rest_reverse('version-detail', kwargs={'pk': version.pk})
        res = self.client.get(url, kwargs)
        data = res.data
        features = data['features']

        eq_(res.status_code, 200)

        # Test values on Version object.
        eq_(data['version'], version.version)
        eq_(data['developer_name'], version.developer_name)
        eq_(data['is_current_version'],
            version == self.app.current_version)
        eq_(data['app'], reverse('app-detail',
                                 kwargs={'pk': self.app.pk}))

        for key in features:
            ok_(getattr(version.features, 'has_' + key))

    def test_get_non_public(self):
        self.app.update(status=amo.STATUS_PENDING)
        url = rest_reverse('version-detail', kwargs={'pk': self.version.pk})
        res = self.client.get(url)
        eq_(res.status_code, 403)

        res = self.anon.get(url)
        eq_(res.status_code, 403)

    def test_get_reviewer_non_public(self):
        self.app.update(status=amo.STATUS_PENDING)
        self.grant_permission(self.profile, 'Apps:Review')
        url = rest_reverse('version-detail', kwargs={'pk': self.version.pk})
        res = self.client.get(url)
        eq_(res.status_code, 200)

    def test_get_owner_non_public(self):
        self.app.update(status=amo.STATUS_PENDING)
        self.app.addonuser_set.create(user=self.user)
        url = rest_reverse('version-detail', kwargs={'pk': self.version.pk})
        res = self.client.get(url)
        eq_(res.status_code, 200)

    def test_get_updated_data(self):
        version = Version.objects.create(addon=self.app, version='1.2')
        version.features.update(has_mp3=True, has_fm=True)
        self.app.update(_latest_version=version, _current_version=version)

        self.test_get()  # Test old version
        self.test_get(version=version)  # Test new version

    def patch(self, features=None):
        data = {
            'features': features or ['fm', 'mp3'],
            'developer_name': "Cee's Vans"
        }
        url = rest_reverse('version-detail', kwargs={'pk': self.version.pk})

        # Uses PUT because Django's test client didn't support PATCH until
        # bug #17797 was resolved.
        res = self.client.put(url, data=json.dumps(data),
                              content_type='application/json')
        return data, res

    def test_patch(self):
        self.app.addonuser_set.create(user=self.user)
        data, res = self.patch()
        eq_(res.status_code, 200)
        self.assertSetEqual(self.version.features.to_keys(),
                            ['has_' + f for f in data['features']])

    def test_patch_bad_features(self):
        self.app.addonuser_set.create(user=self.user)
        data, res = self.patch(features=['bad'])
        eq_(res.status_code, 400)

    def test_patch_no_permission(self):
        data, res = self.patch()
        eq_(res.status_code, 403)

    def test_patch_reviewer_permission(self):
        self.grant_permission(self.profile, 'Apps:Review')
        data, res = self.patch()
        eq_(res.status_code, 200)

    def test_get_deleted_app(self):
        url = rest_reverse('version-detail', kwargs={'pk': self.version.pk})
        self.app.delete()
        res = self.client.get(url)
        eq_(res.status_code, 404)

    def test_get_non_app(self):
        self.app.update(type=amo.ADDON_PERSONA)
        url = rest_reverse('version-detail', kwargs={'pk': self.version.pk})
        res = self.client.get(url)
        eq_(res.status_code, 404)

    def test_delete(self):
        url = rest_reverse('version-detail', kwargs={'pk': self.version.pk})
        res = self.client.delete(url)
        eq_(res.status_code, 405)
