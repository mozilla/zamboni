import json

from django.core.urlresolvers import reverse
from django.test.client import RequestFactory

from mock import patch
from nose.tools import eq_, ok_
from rest_framework.reverse import reverse as rest_reverse

import mkt
from mkt.api.base import get_url
from mkt.api.tests.test_oauth import RestOAuth
from mkt.site.fixtures import fixture
from mkt.site.utils import app_factory, file_factory
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
        self.app.update(status=mkt.STATUS_PENDING)
        url = rest_reverse('version-detail', kwargs={'pk': self.version.pk})
        res = self.client.get(url)
        eq_(res.status_code, 403)

        res = self.anon.get(url)
        eq_(res.status_code, 403)

    def test_get_reviewer_non_public(self):
        self.app.update(status=mkt.STATUS_PENDING)
        self.grant_permission(self.profile, 'Apps:Review')
        url = rest_reverse('version-detail', kwargs={'pk': self.version.pk})
        res = self.client.get(url)
        eq_(res.status_code, 200)

    def test_get_owner_non_public(self):
        self.app.update(status=mkt.STATUS_PENDING)
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
        res = self.client.patch(url, data=json.dumps(data),
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

    def test_delete(self):
        url = rest_reverse('version-detail', kwargs={'pk': self.version.pk})
        res = self.client.delete(url)
        eq_(res.status_code, 405)


class TestVersionStatusViewSet(RestOAuth):
    fixtures = fixture('user_2519')

    def setUp(self):
        self.app = app_factory()
        self.app_url = get_url('app', self.app.pk)
        self.version = self.app.current_version
        self.file = self.version.all_files[0]
        self.request = RequestFactory()
        super(TestVersionStatusViewSet, self).setUp()

    def do_patch(self, data=None, client=None):
        if data is None:
            data = {}
        if client is None:
            client = self.client
        url = rest_reverse('version-status', kwargs={'pk': self.version.pk})
        res = self.client.patch(url, data=json.dumps(data),
                                content_type='application/json')
        return data, res

    def test_has_cors(self):
        url = rest_reverse('version-status', kwargs={'pk': self.version.pk})
        self.assertCORS(self.client.get(url), 'patch')

    def test_patch_anonymous(self):
        data, res = self.do_patch(client=self.anon)
        eq_(res.status_code, 403)

    def test_patch_owner_but_no_permissions(self):
        self.app.addonuser_set.create(user=self.user)
        data, res = self.do_patch()
        eq_(res.status_code, 403)

    def test_patch_permissions(self):
        self.grant_permission(self.user, 'Admin:%')
        data, res = self.do_patch(data={'status': 'pending'})
        eq_(res.status_code, 200)
        eq_(json.loads(res.content), {'status': 'pending',
                                      'app_status': 'public'})
        eq_(self.file.reload().status, mkt.STATUS_PENDING)

    def test_patch_permissions_pk_clash(self):
        # By default, the File and Version objects we are creating share the
        # same pk, and this can hide bugs. Create a new File to specifically
        # test a scenario where they don't share the same pk.
        self.file.delete()
        self.new_file = file_factory(version=self.version)
        self.grant_permission(self.user, 'Admin:%')
        data, res = self.do_patch(data={'status': 'pending'})
        eq_(res.status_code, 200)
        # Note: the app is incomplete since we deleted its public file above
        # and this time we haven't patched is_fully_complete().
        eq_(json.loads(res.content), {'status': 'pending',
                                      'app_status': 'incomplete'})
        eq_(self.new_file.reload().status, mkt.STATUS_PENDING)

    @patch('mkt.webapps.models.Webapp.is_fully_complete')
    def test_patch_permission_status_affecting_app(self, is_fully_complete):
        is_fully_complete.return_value = True
        self.app.update(status=mkt.STATUS_NULL)
        self.file.update(status=mkt.STATUS_NULL)
        self.grant_permission(self.user, 'Admin:%')
        data, res = self.do_patch(data={'status': 'pending'})
        eq_(res.status_code, 200)
        eq_(json.loads(res.content), {'status': 'pending',
                                      'app_status': 'pending'})
        eq_(self.file.reload().status, mkt.STATUS_PENDING)
        eq_(self.app.reload().status, mkt.STATUS_PENDING)

    @patch('mkt.webapps.models.Webapp.is_fully_complete')
    def test_patch_permission_status_not_affecting(self, is_fully_complete):
        is_fully_complete.return_value = False
        self.app.update(status=mkt.STATUS_NULL)
        self.file.update(status=mkt.STATUS_NULL)
        self.grant_permission(self.user, 'Admin:%')
        data, res = self.do_patch(data={'status': 'pending'})
        eq_(res.status_code, 200)
        eq_(json.loads(res.content), {'status': 'pending',
                                      'app_status': 'incomplete'})
        eq_(self.file.reload().status, mkt.STATUS_PENDING)
        eq_(self.app.reload().status, mkt.STATUS_NULL)

    def test_patch_permissions_status(self):
        self.grant_permission(self.user, 'Admin:%')
        data, res = self.do_patch(data={'status': 'incomplete'})
        eq_(res.status_code, 200)
        eq_(json.loads(res.content), {'status': 'incomplete',
                                      'app_status': 'public'})
        eq_(self.file.reload().status, mkt.STATUS_NULL)

        data, res = self.do_patch(data={'status': 'public'})
        eq_(res.status_code, 200)
        eq_(json.loads(res.content), {'status': 'public',
                                      'app_status': 'public'})
        eq_(self.file.reload().status, mkt.STATUS_PUBLIC)

    def test_patch_wrong_status(self):
        self.grant_permission(self.user, 'Admin:%')
        data, res = self.do_patch(data={'status': 'lol'})
        eq_(res.status_code, 400)

        data, res = self.do_patch()
        eq_(res.status_code, 400)
