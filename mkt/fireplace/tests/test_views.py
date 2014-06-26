import json
from urlparse import urlparse

from django.core.urlresolvers import reverse
from django.db.models.query import QuerySet

from mock import patch
from nose.tools import eq_, ok_
from test_utils import RequestFactory

import mkt
from amo.tests import app_factory, ESTestCase, TestCase
from mkt.api.tests import BaseAPI
from mkt.api.tests.test_oauth import RestOAuth
from mkt.collections.constants import COLLECTIONS_TYPE_BASIC
from mkt.collections.models import Collection
from mkt.fireplace.serializers import FireplaceAppSerializer
from mkt.search.utils import S
from mkt.site.fixtures import fixture
from mkt.webapps.models import AddonUser, Installed, Webapp
from mkt.users.models import UserProfile


# https://bugzilla.mozilla.org/show_bug.cgi?id=958608#c1 and #c2.
FIREPLACE_EXCLUDED_FIELDS = (
    'absolute_url', 'app_type', 'created', 'default_locale', 'payment_account',
    'regions', 'resource_uri', 'supported_locales', 'tags', 'upsold',
    'versions', 'weekly_downloads')


class TestAppDetail(BaseAPI):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        super(TestAppDetail, self).setUp()
        self.url = reverse('fireplace-app-detail', kwargs={'pk': 337141})

    def test_get(self):
        res = self.client.get(self.url)
        data = json.loads(res.content)
        eq_(data['id'], 337141)
        for field in FIREPLACE_EXCLUDED_FIELDS:
            ok_(not field in data, field)
        for field in FireplaceAppSerializer.Meta.fields:
            ok_(field in data, field)

    def test_get_slug(self):
        Webapp.objects.get(pk=337141).update(app_slug='foo')
        res = self.client.get(reverse('fireplace-app-detail',
                                      kwargs={'pk': 'foo'}))
        data = json.loads(res.content)
        eq_(data['id'], 337141)

    def test_others(self):
        url = reverse('fireplace-app-list')
        self._allowed_verbs(self.url, ['get'])
        self._allowed_verbs(url, [])


class TestFeaturedSearchView(RestOAuth, ESTestCase):
    fixtures = fixture('user_2519', 'webapp_337141')

    def setUp(self):
        super(TestFeaturedSearchView, self).setUp()
        self.webapp = Webapp.objects.get(pk=337141)
        collection = Collection.objects.create(name='Hi', description='Mom',
            collection_type=COLLECTIONS_TYPE_BASIC, is_public=True)
        collection.add_app(self.webapp)
        self.reindex(Webapp, 'webapp')
        self.url = reverse('fireplace-featured-search-api')

    def test_get(self):
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        objects = res.json['objects']
        eq_(len(objects), 1)
        data = objects[0]
        eq_(data['id'], 337141)
        for field in FIREPLACE_EXCLUDED_FIELDS:
            ok_(not field in data, field)
        for field in FireplaceAppSerializer.Meta.fields:
            ok_(field in data, field)

        ok_('collections' in res.json)
        eq_(res.json['collections'][0]['name'], {u'en-US': u'Hi'})
        data = res.json['collections'][0]['apps'][0]
        for field in FIREPLACE_EXCLUDED_FIELDS:
            ok_(not field in data, field)
        for field in FireplaceAppSerializer.Meta.fields:
            ok_(field in data, field)
        ok_('featured' in res.json)
        ok_('operator' in res.json)

    def test_only_64px_icons(self):
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        objects = res.json['objects']
        data = objects[0]['icons']
        eq_(len(data), 1)
        eq_(urlparse(data['64'])[0:3],
            urlparse(self.webapp.get_icon_url(64))[0:3])


class TestCollectionViewSet(RestOAuth, ESTestCase):
    fixtures = fixture('user_2519', 'webapp_337141')

    def setUp(self):
        super(TestCollectionViewSet, self).setUp()
        self.webapp = Webapp.objects.get(pk=337141)
        collection = Collection.objects.create(name='Hi', description='Mom',
            collection_type=COLLECTIONS_TYPE_BASIC, is_public=True)
        collection.add_app(self.webapp)
        self.reindex(Webapp, 'webapp')
        self.url = reverse('fireplace-collection-detail',
                           kwargs={'pk': collection.pk})

    def test_get(self):
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        eq_(res.json['name'], {u'en-US': u'Hi'})
        data = res.json['apps'][0]
        for field in FIREPLACE_EXCLUDED_FIELDS:
            ok_(not field in data, field)
        for field in FireplaceAppSerializer.Meta.fields:
            ok_(field in data, field)

    @patch('mkt.collections.serializers.CollectionMembershipField.to_native')
    def test_get_preview(self, mock_field_to_native):
        mock_field_to_native.return_value = []
        res = self.client.get(self.url, {'preview': 1})
        eq_(res.status_code, 200)
        eq_(res.json['name'], {u'en-US': u'Hi'})
        eq_(res.json['apps'], [])

        eq_(mock_field_to_native.call_count, 1)
        ok_(isinstance(mock_field_to_native.call_args[0][0], QuerySet))
        eq_(mock_field_to_native.call_args[1].get('use_es', False), False)

    @patch('mkt.collections.serializers.CollectionMembershipField.to_native')
    def test_no_get_preview(self, mock_field_to_native):
        mock_field_to_native.return_value = []
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        eq_(res.json['name'], {u'en-US': u'Hi'})
        eq_(res.json['apps'], [])

        eq_(mock_field_to_native.call_count, 1)
        ok_(isinstance(mock_field_to_native.call_args[0][0], S))
        eq_(mock_field_to_native.call_args[1].get('use_es', False), True)


class TestSearchView(RestOAuth, ESTestCase):
    fixtures = fixture('user_2519', 'webapp_337141')

    def setUp(self):
        super(TestSearchView, self).setUp()
        self.webapp = Webapp.objects.get(pk=337141)
        self.reindex(Webapp, 'webapp')
        self.url = reverse('fireplace-search-api')

    def test_get(self):
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        objects = res.json['objects']
        eq_(len(objects), 1)
        data = objects[0]
        eq_(data['id'], 337141)
        for field in FIREPLACE_EXCLUDED_FIELDS:
            ok_(not field in data, field)
        for field in FireplaceAppSerializer.Meta.fields:
            ok_(field in data, field)
        ok_(not 'featured' in res.json)
        ok_(not 'collections' in res.json)
        ok_(not 'operator' in res.json)

    def test_anonymous_user(self):
        res = self.anon.get(self.url)
        eq_(res.status_code, 200)
        data = res.json['objects'][0]
        eq_(data['user'], None)

        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        data = res.json['objects'][0]
        eq_(data['user'], None)


class TestConsumerInfoView(RestOAuth, TestCase):
    fixtures = fixture('user_2519')

    def setUp(self):
        super(TestConsumerInfoView, self).setUp()
        self.request = RequestFactory().get('/')
        self.url = reverse('fireplace-consumer-info')
        self.user = UserProfile.objects.get(pk=2519)

    @patch('mkt.regions.middleware.RegionMiddleware.region_from_request')
    def test_no_user_just_region(self, region_from_request):
        region_from_request.return_value = mkt.regions.UK
        res = self.anon.get(self.url)
        data = json.loads(res.content)
        eq_(data['region'], 'uk')
        ok_(not 'apps' in data)

    @patch('mkt.regions.middleware.RegionMiddleware.region_from_request')
    def test_with_user_developed(self, region_from_request):
        region_from_request.return_value = mkt.regions.BR
        developed_app = app_factory()
        AddonUser.objects.create(user=self.user, addon=developed_app)
        self.client.login(username=self.user.email, password='password')
        res = self.client.get(self.url)
        data = json.loads(res.content)
        eq_(data['region'], 'br')
        eq_(data['apps']['installed'], [])
        eq_(data['apps']['developed'], [developed_app.pk])
        eq_(data['apps']['purchased'], [])

    @patch('mkt.regions.middleware.RegionMiddleware.region_from_request')
    def test_with_user_installed(self, region_from_request):
        region_from_request.return_value = mkt.regions.BR
        installed_app = app_factory()
        Installed.objects.create(user=self.user, addon=installed_app)
        self.client.login(username=self.user.email, password='password')
        res = self.client.get(self.url)
        data = json.loads(res.content)
        eq_(data['region'], 'br')
        eq_(data['apps']['installed'], [installed_app.pk])
        eq_(data['apps']['developed'], [])
        eq_(data['apps']['purchased'], [])

    @patch('mkt.users.models.UserProfile.purchase_ids')
    @patch('mkt.regions.middleware.RegionMiddleware.region_from_request')
    def test_with_user_purchased(self, region_from_request, purchase_ids):
        region_from_request.return_value = mkt.regions.BR
        purchased_app = app_factory()
        purchase_ids.return_value = [purchased_app.pk]
        self.client.login(username=self.user.email, password='password')
        res = self.client.get(self.url)
        data = json.loads(res.content)
        eq_(data['region'], 'br')
        eq_(data['apps']['installed'], [])
        eq_(data['apps']['developed'], [])
        eq_(data['apps']['purchased'], [purchased_app.pk])

    def test_no_switches(self):
        res = self.client.get(self.url)
        data = json.loads(res.content)
        eq_(len(data['waffle']['switches']), 0)

    def test_with_switches(self):
        self.create_switch('wax-on', db=True)
        res = self.client.get(self.url)
        data = json.loads(res.content)
        eq_(len(data['waffle']['switches']), 1)
        eq_(data['waffle']['switches'], ['wax-on'])
