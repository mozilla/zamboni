# -*- coding: utf-8 -*-
import json
import os

from django.core.urlresolvers import reverse
from django.utils.text import slugify

import mock
from elasticsearch_dsl.search import Search
from mpconstants import collection_colors as coll_colors
from nose.tools import eq_, ok_

import mkt
import mkt.carriers
import mkt.feed.constants as feed
import mkt.regions
from mkt.api.tests.test_oauth import RestOAuth
from mkt.constants import applications
from mkt.feed.models import (FeedApp, FeedBrand, FeedCollection, FeedItem,
                             FeedShelf)
from mkt.feed.tests.test_models import FeedAppMixin, FeedTestMixin
from mkt.feed.views import FeedView
from mkt.fireplace.tests.test_views import assert_fireplace_app
from mkt.operators.models import OperatorPermission
from mkt.site.fixtures import fixture
from mkt.site.tests import app_factory, ESTestCase, TestCase
from mkt.tags.models import Tag
from mkt.users.models import UserProfile
from mkt.webapps.models import Preview, Webapp
from mkt.websites.models import Website
from mkt.websites.utils import website_factory


TEST_DIR = os.path.dirname(os.path.abspath(__file__))
FILES_DIR = os.path.join(TEST_DIR, 'files')


# Mock this constant through the whole file so we can have one-app collections.
feed.MIN_APPS_COLLECTION = 1


class BaseTestFeedItemViewSet(RestOAuth, FeedTestMixin):
    def setUp(self):
        super(BaseTestFeedItemViewSet, self).setUp()
        self.profile = self.user

    def feed_permission(self):
        """
        Grant the Feed:Curate permission to the authenticating user.
        """
        self.grant_permission(self.profile, 'Feed:Curate')


class BaseTestFeedESView(ESTestCase):
    def setUp(self):
        Webapp.get_indexer().index_ids(
            list(Webapp.objects.values_list('id', flat=True)))
        super(BaseTestFeedESView, self).setUp()

    def tearDown(self):
        for model in (FeedApp, FeedBrand, FeedCollection, FeedShelf,
                      FeedItem):
            model.get_indexer().unindexer(_all=True)
        super(BaseTestFeedESView, self).tearDown()

    def _refresh(self):
        self.refresh('mkt_feed_app')
        self.refresh('mkt_feed_brand')
        self.refresh('mkt_feed_collection')
        self.refresh('mkt_feed_shelf')
        self.refresh('mkt_feed_item')
        self.refresh('webapp')


class BaseTestGroupedApps(object):
    """
    Base class containing utilities for testing grouped app collections.
    """

    def ungrouped_apps(self):
        apps = [app_factory() for i in xrange(3)]
        return [app.pk for app in apps]

    def grouped_apps(self):
        ret = []
        for name in ['Games', 'Productivity', 'Lifestyle']:
            apps = [app_factory() for i in xrange(2)]
            ret.append({
                'apps': [app.pk for app in apps],
                'name': {
                    'en-US': name,
                    'fr': name[::-1]
                }
            })
        return ret

    def assertGroupedAppsEqual(self, grouped_apps, data):
        """
        Passed a list of dicts formed similar to the return value from
        self.grouped_apps() and a collection serialization, asserts that the
        apps in the serialization are in the correct groups as specified by the
        list of dicts.
        """
        compare = {}
        for group in grouped_apps:
            for app in group['apps']:
                compare[app] = group['name']
        for app in data['apps']:
            eq_(compare[app['id']], app['group'])


class TestFeedItemViewSetList(FeedAppMixin, BaseTestFeedItemViewSet):
    """
    Tests the handling of GET requests to the list endpoint of FeedItemViewSet.
    """
    fixtures = BaseTestFeedItemViewSet.fixtures + FeedAppMixin.fixtures

    def setUp(self):
        super(TestFeedItemViewSetList, self).setUp()
        self.url = reverse('api-v2:feeditems-list')
        self.create_feedapps()
        self.item = FeedItem.objects.create(app=self.feedapps[0])

    def list(self, client, **kwargs):
        res = client.get(self.url, kwargs)
        data = json.loads(res.content)
        return res, data

    def test_list_anonymous(self):
        res, data = self.list(self.anon)
        eq_(res.status_code, 200)
        eq_(data['meta']['total_count'], 1)
        eq_(data['objects'][0]['id'], self.item.id)

    def test_list_no_permission(self):
        res, data = self.list(self.client)
        eq_(res.status_code, 200)
        eq_(data['meta']['total_count'], 1)
        eq_(data['objects'][0]['id'], self.item.id)

    def test_list_with_permission(self):
        self.feed_permission()
        res, data = self.list(self.client)
        eq_(res.status_code, 200)
        eq_(data['meta']['total_count'], 1)
        eq_(data['objects'][0]['id'], self.item.id)

    def test_filter_region(self):
        self.item.update(region=2)
        res, data = self.list(self.client, region='restofworld')
        eq_(data['meta']['total_count'], 0)
        res, data = self.list(self.client, region='us')
        eq_(data['meta']['total_count'], 1)
        eq_(data['objects'][0]['id'], self.item.id)

    def test_filter_carrier(self):
        self.item.update(carrier=16)
        res, data = self.list(self.client, carrier='vimpelcom')
        eq_(data['meta']['total_count'], 0)
        res, data = self.list(self.client, carrier='tmn')
        eq_(data['meta']['total_count'], 1)
        eq_(data['objects'][0]['id'], self.item.id)

    def test_filter_bad_region(self):
        res, data = self.list(self.client, region='kantoregion')
        eq_(data['meta']['total_count'], 1)

    def test_filter_bad_carrier(self):
        res, data = self.list(self.client, carrier='carrierpigeons')
        eq_(data['meta']['total_count'], 1)


class TestFeedItemViewSetCreate(FeedAppMixin, BaseTestFeedItemViewSet):
    """
    Tests the handling of POST requests to the list endpoint of
    FeedItemViewSet.
    """
    fixtures = BaseTestFeedItemViewSet.fixtures + FeedAppMixin.fixtures

    def setUp(self):
        super(TestFeedItemViewSetCreate, self).setUp()
        self.create_feedapps()
        self.url = reverse('api-v2:feeditems-list')

    def create(self, client, **kwargs):
        res = client.post(self.url, json.dumps(kwargs))
        data = json.loads(res.content)
        return res, data

    def test_create_anonymous(self):
        res, data = self.create(self.anon, app=self.feedapps[0].pk)
        eq_(res.status_code, 403)

    def test_create_no_permission(self):
        res, data = self.create(self.client, app=self.feedapps[0].pk)
        eq_(res.status_code, 403)

    def test_create_with_permission(self):
        self.feed_permission()
        res, data = self.create(self.client, app=self.feedapps[0].pk,
                                item_type=feed.FEED_TYPE_APP,
                                carrier=mkt.carriers.TELEFONICA.id,
                                region=mkt.regions.BRA.id)
        eq_(res.status_code, 201)
        self.assertCORS(res, 'get', 'delete', 'post', 'put', 'patch')
        eq_(data['app']['id'], self.feedapps[0].pk)

    def test_create_no_data(self):
        self.feed_permission()
        res, data = self.create(self.client)
        eq_(res.status_code, 400)


class TestFeedItemViewSetDetail(FeedAppMixin, BaseTestFeedItemViewSet):
    """
    Tests the handling of GET requests to detail endpoints of FeedItemViewSet.
    """
    fixtures = BaseTestFeedItemViewSet.fixtures + FeedAppMixin.fixtures

    def setUp(self):
        super(TestFeedItemViewSetDetail, self).setUp()
        self.create_feedapps()
        self.item = FeedItem.objects.create(app=self.feedapps[0])
        self.url = reverse('api-v2:feeditems-detail',
                           kwargs={'pk': self.item.pk})

    def detail(self, client, **kwargs):
        res = client.get(self.url, kwargs)
        data = json.loads(res.content)
        return res, data

    def test_list_anonymous(self):
        res, data = self.detail(self.anon)
        eq_(res.status_code, 200)
        eq_(data['id'], self.item.pk)

    def test_list_no_permission(self):
        res, data = self.detail(self.client)
        eq_(res.status_code, 200)
        eq_(data['id'], self.item.pk)

    def test_list_with_permission(self):
        self.feed_permission()
        res, data = self.detail(self.client)
        eq_(res.status_code, 200)
        eq_(data['id'], self.item.pk)


class TestFeedItemViewSetUpdate(FeedAppMixin, BaseTestFeedItemViewSet):
    """
    Tests the handling of PATCH requests to detail endpoints of
    FeedItemViewSet.
    """
    fixtures = BaseTestFeedItemViewSet.fixtures + FeedAppMixin.fixtures

    def setUp(self):
        super(TestFeedItemViewSetUpdate, self).setUp()
        self.create_feedapps()
        self.item = FeedItem.objects.create(app=self.feedapps[0])
        self.url = reverse('api-v2:feeditems-detail',
                           kwargs={'pk': self.item.pk})

    def update(self, client, **kwargs):
        res = client.patch(self.url, json.dumps(kwargs))
        data = json.loads(res.content)
        return res, data

    def test_update_anonymous(self):
        res, data = self.update(self.anon)
        eq_(res.status_code, 403)

    def test_update_no_permission(self):
        res, data = self.update(self.client)
        eq_(res.status_code, 403)

    def test_update_with_permission(self):
        self.feed_permission()
        res, data = self.update(self.client, item_type=feed.FEED_TYPE_APP,
                                region=mkt.regions.USA.id)
        eq_(res.status_code, 200)
        eq_(data['id'], self.item.pk)
        eq_(data['region'], mkt.regions.USA.slug)

    def test_update_no_items(self):
        self.feed_permission()
        res, data = self.update(self.client, app=None)
        eq_(res.status_code, 400)


class TestFeedItemViewSetDelete(FeedAppMixin, BaseTestFeedItemViewSet):
    """
    Tests the handling of DELETE requests to detail endpoints of
    FeedItemViewSet.
    """
    fixtures = BaseTestFeedItemViewSet.fixtures + FeedAppMixin.fixtures

    def setUp(self):
        super(TestFeedItemViewSetDelete, self).setUp()
        self.create_feedapps()
        self.item = FeedItem.objects.create(app=self.feedapps[0])
        self.url = reverse('api-v2:feeditems-detail',
                           kwargs={'pk': self.item.pk})

    def delete(self, client, **kwargs):
        res = client.delete(self.url)
        data = json.loads(res.content) if res.content else ''
        return res, data

    def test_update_anonymous(self):
        res, data = self.delete(self.anon)
        eq_(res.status_code, 403)

    def test_update_no_permission(self):
        res, data = self.delete(self.client)
        eq_(res.status_code, 403)

    def test_update_with_permission(self):
        self.feed_permission()
        res, data = self.delete(self.client)
        eq_(res.status_code, 204)


class BaseTestFeedAppViewSet(FeedAppMixin, RestOAuth):
    fixtures = FeedAppMixin.fixtures + RestOAuth.fixtures

    def setUp(self):
        super(BaseTestFeedAppViewSet, self).setUp()
        self.app = Webapp.objects.get(pk=337141)
        self.profile = self.user

    def feed_permission(self):
        """
        Grant the Feed:Curate permission to the authenticating user.
        """
        self.grant_permission(self.profile, 'Feed:Curate')


class TestFeedAppViewSetList(BaseTestFeedAppViewSet):
    """
    Tests the handling of GET requests to the list endpoint of FeedAppViewSet.
    """
    num = 2

    def setUp(self):
        super(TestFeedAppViewSetList, self).setUp()
        self.url = reverse('api-v2:feedapps-list')
        self.create_feedapps(self.num)

    def list(self, client):
        res = client.get(self.url)
        data = json.loads(res.content)
        return res, data

    def _test_list(self, client):
        res, data = self.list(client)
        eq_(res.status_code, 200)
        objects = data['objects']
        eq_(data['meta']['total_count'], self.num)
        eq_(len(objects), self.num)
        self.assertSetEqual([obj['id'] for obj in objects],
                            [fa.id for fa in self.feedapps])

    def test_list_anonymous(self):
        self._test_list(self.anon)

    def test_list_no_permission(self):
        self._test_list(self.client)

    def test_list_with_permission(self):
        self.feed_permission()
        self._test_list(self.client)


class TestFeedAppViewSetCreate(BaseTestFeedAppViewSet):
    """
    Tests the handling of POST requests to the list endpoint of FeedAppViewSet.
    """
    fixtures = BaseTestFeedAppViewSet.fixtures

    def setUp(self):
        super(TestFeedAppViewSetCreate, self).setUp()
        self.url = reverse('api-v2:feedapps-list')

    def create(self, client, **kwargs):
        res = client.post(self.url, json.dumps(kwargs))
        data = json.loads(res.content)
        return res, data

    def test_create_anonymous(self):
        res, data = self.create(self.anon)
        eq_(res.status_code, 403)

    def test_create_no_permission(self):
        res, data = self.create(self.client, **self.feedapp_data)
        eq_(res.status_code, 403)

    def test_create_with_permission(self):
        self.feed_permission()
        res, data = self.create(self.client, **self.feedapp_data)
        eq_(res.status_code, 201)
        eq_(data['app']['id'], self.feedapp_data['app'])
        eq_(data['description'], self.feedapp_data['description'])
        eq_(data['slug'], self.feedapp_data['slug'])
        eq_(data['type'], self.feedapp_data['type'])

        self.assertCORS(res, 'get', 'delete', 'patch', 'post', 'put')
        return res, data

    def test_create_with_color(self):
        color = coll_colors.COLLECTION_COLORS.keys()[0]
        self.feedapp_data.update(color=color)
        res, data = self.test_create_with_permission()
        eq_(data['color'], color)

    def test_create_with_preview(self):
        preview = Preview.objects.create(addon=self.app, position=0)
        self.feedapp_data.update(preview=preview.pk)
        res, data = self.test_create_with_permission()
        eq_(data['preview']['id'], preview.id)

    def test_create_with_pullquote(self):
        self.feedapp_data.update(**self.pullquote_data)
        res, data = self.test_create_with_permission()
        for field, value in self.pullquote_data.iteritems():
            eq_(data[field], value)

    def test_create_slug_xss(self):
        xss_slug = u"<script>alert('yo.');</script>"
        self.feed_permission()
        self.feedapp_data.update(slug=xss_slug)
        res, data = self.create(self.client, **self.feedapp_data)
        eq_(data['slug'], slugify(xss_slug))

    def test_create_with_pullquote_no_rating(self):
        del self.pullquote_data['pullquote_rating']
        self.test_create_with_pullquote()

    def test_create_with_pullquote_no_text(self):
        self.feed_permission()
        del self.pullquote_data['pullquote_text']
        self.feedapp_data.update(**self.pullquote_data)
        res, data = self.create(self.client, **self.feedapp_data)
        eq_(res.status_code, 400)
        eq_(data, {u'non_field_errors':
                   [u'Pullquote text required if rating or '
                    'attribution is defined.']})

    def test_create_with_pullquote_bad_rating_fractional(self):
        self.feed_permission()
        self.pullquote_data['pullquote_rating'] = 4.5
        self.feedapp_data.update(**self.pullquote_data)
        res, data = self.create(self.client, **self.feedapp_data)
        eq_(res.status_code, 400)
        ok_('pullquote_rating' in data)

    def test_create_with_pullquote_bad_rating_high(self):
        self.feed_permission()
        self.pullquote_data['pullquote_rating'] = 6
        self.feedapp_data.update(**self.pullquote_data)
        res, data = self.create(self.client, **self.feedapp_data)
        eq_(res.status_code, 400)
        ok_('pullquote_rating' in data)

    def test_create_with_pullquote_bad_rating_low(self):
        self.feed_permission()
        self.pullquote_data['pullquote_rating'] = -1
        self.feedapp_data.update(**self.pullquote_data)
        res, data = self.create(self.client, **self.feedapp_data)
        eq_(res.status_code, 400)
        ok_('pullquote_rating' in data)

    @mock.patch('mkt.feed.views.pngcrush_image.delay')
    @mock.patch('mkt.feed.views.requests.get')
    def test_create_with_background_image(self, download_mock, crush_mock):
        res_mock = mock.Mock()
        res_mock.status_code = 200
        res_mock.content = open(
            os.path.join(FILES_DIR, 'bacon.jpg'), 'r').read()
        download_mock.return_value = res_mock

        self.feed_permission()
        self.feedapp_data.update(
            {'background_image_upload_url': 'ngokevin.com'})  # SEO.
        res, data = self.create(self.client, **self.feedapp_data)

        feedapp = FeedApp.objects.all()[0]
        ok_(data['background_image'].endswith(feedapp.image_hash))
        eq_(crush_mock.call_args_list[0][0][0], feedapp.image_path())

    @mock.patch('mkt.feed.views.requests.get')
    def test_background_image_404(self, download_mock):
        res_mock = mock.Mock()
        res_mock.status_code = 404
        res_mock.content = ''
        download_mock.return_value = res_mock

        self.feed_permission()
        self.feedapp_data.update(
            {'background_image_upload_url': 'ngokevin.com'})  # SEO.
        res, data = self.create(self.client, **self.feedapp_data)

        eq_(res.status_code, 400)

    def test_create_no_data(self):
        self.feed_permission()
        res, data = self.create(self.client)
        eq_(res.status_code, 400)


class TestFeedAppViewSetDetail(BaseTestFeedAppViewSet):
    """
    Tests the handling of GET requests to detail endpoints of FeedAppViewSet.
    """

    def setUp(self):
        super(TestFeedAppViewSetDetail, self).setUp()
        self.feedapp = self.create_feedapps(1)[0]
        self.url = reverse('api-v2:feedapps-detail',
                           kwargs={'pk': self.feedapp.pk})

    def detail(self, client, **kwargs):
        res = client.get(self.url)
        data = json.loads(res.content)
        return res, data

    def _test_detail(self, client):
        res, data = self.detail(client)
        eq_(res.status_code, 200)
        eq_(data['id'], self.feedapp.pk)
        eq_(data['url'], self.url)
        eq_(data['app']['id'], self.feedapp.app.id)
        ok_(not data['preview'])
        ok_(not data['pullquote_text'])
        return res, data

    def test_detail_anonymous(self):
        self._test_detail(self.anon)

    def test_detail_no_permission(self):
        self._test_detail(self.client)

    def test_detail_with_permission(self):
        self.feed_permission()
        self._test_detail(self.client)

    def test_with_image(self):
        self.feedapp = self.create_feedapps(1, image_hash='abcdefgh')[0]
        self.url = reverse('api-v2:feedapps-detail',
                           kwargs={'pk': self.feedapp.pk})
        res, data = self._test_detail(self.client)
        ok_(data.get('background_image'))


class TestFeedAppViewSetUpdate(BaseTestFeedAppViewSet):
    """
    Tests the handling of PATCH requests to detail endpoints of FeedAppViewSet.
    """
    fixtures = BaseTestFeedAppViewSet.fixtures

    def setUp(self):
        super(TestFeedAppViewSetUpdate, self).setUp()
        self.feedapp = self.create_feedapps(1)[0]
        self.url = reverse('api-v2:feedapps-detail',
                           kwargs={'pk': self.feedapp.pk})

    def update(self, client, **kwargs):
        res = client.patch(self.url, json.dumps(kwargs))
        data = json.loads(res.content)
        return res, data

    def test_update_anonymous(self):
        res, data = self.update(self.anon)
        eq_(res.status_code, 403)

    def test_update_no_permission(self):
        res, data = self.update(self.client, **self.feedapp_data)
        eq_(res.status_code, 403)

    def test_update_with_permission(self):
        self.feed_permission()
        new_description = {
            'en-US': u"BastaCorp's famous pan-fried potatoes",
            'fr': u'pommes de terre sautées de BastaCorp'
        }
        res, data = self.update(self.client, description=new_description)
        eq_(res.status_code, 200)
        eq_(data['description'], new_description)

    def test_update_invalid_app(self):
        self.feed_permission()
        res, data = self.update(self.client, app=1)
        eq_(res.status_code, 400)
        ok_('app' in data)

    def test_update_no_app(self):
        self.feed_permission()
        res, data = self.update(self.client, app=None)
        eq_(res.status_code, 400)
        ok_('app' in data)


class TestFeedAppViewSetDelete(BaseTestFeedAppViewSet):
    """
    Tests the handling of DELETE requests to detail endpoints of
    FeedAppViewSet.
    """

    def setUp(self):
        super(TestFeedAppViewSetDelete, self).setUp()
        self.feedapp = self.create_feedapps(1)[0]
        self.url = reverse('api-v2:feedapps-detail',
                           kwargs={'pk': self.feedapp.pk})

    def delete(self, client, **kwargs):
        res = client.delete(self.url)
        data = json.loads(res.content) if res.content else ''
        return res, data

    def test_delete_anonymous(self):
        res, data = self.delete(self.anon)
        eq_(res.status_code, 403)

    def test_delete_no_permission(self):
        res, data = self.delete(self.client)
        eq_(res.status_code, 403)

    def test_delete_with_permission(self):
        self.feed_permission()
        res, data = self.delete(self.client)
        eq_(res.status_code, 204)


class BaseTestFeedCollection(object):
    obj_data = None
    model = None
    obj = None
    serializer = None
    url_basename = None

    def setUp(self):
        super(BaseTestFeedCollection, self).setUp()
        self.list_url = reverse('api-v2:%s-list' % self.url_basename)

    def data(self, **kwargs):
        data = dict(self.obj_data)
        data.update(kwargs)
        return data

    def make_apps(self):
        return [app_factory() for i in xrange(3)]

    def make_item(self, **addtl):
        obj_data = self.data(slug='sprout')
        obj_data.update(addtl)
        self.item = self.model.objects.create(**obj_data)
        self.detail_url = reverse('api-v2:%s-detail' % self.url_basename,
                                  kwargs={'pk': self.item.pk})

    def feed_permission(self):
        self.grant_permission(self.profile, 'Feed:Curate')

    def get(self, client):
        self.make_item()
        res = client.get(self.detail_url)
        data = json.loads(res.content)
        return res, data

    def list(self, client):
        self.make_item()
        res = client.get(self.list_url)
        data = json.loads(res.content)
        return res, data

    def create(self, client, **kwargs):
        res = client.post(self.list_url, json.dumps(kwargs))
        data = json.loads(res.content)
        return res, data

    def update(self, client, **kwargs):
        self.make_item()
        res = client.patch(self.detail_url, json.dumps(kwargs))
        data = json.loads(res.content)
        return res, data

    def delete(self, client):
        self.make_item()
        res = client.delete(self.detail_url)
        data = json.loads(res.content or '{}')
        return res, data

    def test_get_anonymous(self):
        res, data = self.get(self.anon)
        eq_(res.status_code, 200)
        eq_(data['id'], self.item.pk)

    def test_get_no_permission(self):
        res, data = self.get(self.client)
        eq_(res.status_code, 200)
        eq_(data['id'], self.item.pk)

    def test_get_with_permission(self):
        self.feed_permission()
        res, data = self.get(self.client)
        eq_(res.status_code, 200)
        eq_(data['id'], self.item.pk)

    def test_list_anonymous(self):
        res, data = self.list(self.anon)
        eq_(res.status_code, 200)
        eq_(data['meta']['total_count'], 1)
        eq_(data['objects'][0]['id'], self.item.id)

    def test_list_no_permission(self):
        res, data = self.list(self.client)
        eq_(res.status_code, 200)
        eq_(data['meta']['total_count'], 1)
        eq_(data['objects'][0]['id'], self.item.id)

    def test_list_with_permission(self):
        self.feed_permission()
        res, data = self.list(self.client)
        eq_(res.status_code, 200)
        eq_(data['meta']['total_count'], 1)
        eq_(data['objects'][0]['id'], self.item.id)

    def test_list_with_apps(self):
        self.feed_permission()
        apps = [app.pk for app in self.make_apps()]
        data = dict(self.obj_data)
        data.update({'apps': apps})
        self.create(self.client, **data)

        res, data = self.list(self.client)
        self.assertSetEqual(
            apps, [app['id'] for app in data['objects'][1]['apps']])

    def test_create_anonymous(self):
        res, data = self.create(self.anon, **self.obj_data)
        eq_(res.status_code, 403)

    def test_create_no_permission(self):
        res, data = self.create(self.client, **self.obj_data)
        eq_(res.status_code, 403)

    def test_create_with_permission(self):
        self.feed_permission()
        res, data = self.create(self.client, **self.obj_data)
        eq_(res.status_code, 201)
        for name, value in self.obj_data.iteritems():
            eq_(value, data[name])

    def test_create_slug_xss(self):
        self.feed_permission()
        obj_data = dict(self.obj_data)
        xss_slug = u"<script>alert('yo.');</script>"
        if 'slug' in obj_data:
            obj_data.update({'slug': xss_slug})
        res, data = self.create(self.client, **obj_data)
        eq_(data['slug'], slugify(xss_slug))

    def test_create_with_apps(self):
        self.feed_permission()
        apps = [app.pk for app in self.make_apps()]
        data = dict(self.obj_data)
        data.update({'apps': apps})
        res, data = self.create(self.client, **data)
        eq_(res.status_code, 201)
        eq_(apps, [app['id'] for app in data['apps']])

    def test_create_no_data(self):
        self.feed_permission()
        res, data = self.create(self.client)
        eq_(res.status_code, 400)

    def test_create_duplicate_slug(self):
        self.feed_permission()
        obj_data = self.data()
        res1, data1 = self.create(self.client, **obj_data)
        eq_(res1.status_code, 201,
            getattr(res1, 'json', 'unexpected status code'))
        eq_(obj_data['slug'], data1['slug'])

        res2, data2 = self.create(self.client, **obj_data)
        eq_(res2.status_code, 201)
        eq_(obj_data['slug'] + '-1', data2['slug'])

    def test_update_anonymous(self):
        res, data = self.update(self.anon)
        eq_(res.status_code, 403)

    def test_update_no_permission(self):
        res, data = self.update(self.client)
        eq_(res.status_code, 403)

    def test_update_with_permission(self):
        self.feed_permission()
        new_slug = 'french_fries'
        res, data = self.update(self.client, slug=new_slug)
        eq_(res.status_code, 200)
        eq_(data['id'], self.item.pk)
        eq_(data['slug'], new_slug)

    def test_update_with_apps(self):
        self.feed_permission()
        new_apps = [app.pk for app in self.make_apps()]
        res, data = self.update(self.client, apps=new_apps)
        eq_(res.status_code, 200)
        eq_(data['id'], self.item.pk)
        eq_(new_apps, [app['id'] for app in data['apps']])

    def test_delete_anonymous(self):
        res, data = self.delete(self.anon)
        eq_(res.status_code, 403)

    def test_delete_no_permission(self):
        res, data = self.delete(self.client)
        eq_(res.status_code, 403)

    def test_delete_with_permission(self):
        self.feed_permission()
        res, data = self.delete(self.client)
        eq_(res.status_code, 204)


class TestFeedBrandViewSet(BaseTestFeedCollection, RestOAuth):
    obj_data = {
        'layout': 'grid',
        'type': 'hidden-gem',
        'slug': 'potato'
    }
    model = FeedBrand
    url_basename = 'feedbrands'


class TestFeedCollectionViewSet(BaseTestGroupedApps, BaseTestFeedCollection,
                                RestOAuth):
    obj_data = {
        'slug': 'potato',
        'type': 'promo',
        'color': coll_colors.COLLECTION_COLORS.keys()[0],
        'description': {'en-US': 'Potato french fries'},
        'name': {'en-US': 'Deep Fried'}
    }
    model = FeedCollection
    url_basename = 'feedcollections'

    def test_create_missing_name(self):
        self.feed_permission()
        obj_data = self.data()
        del obj_data['name']
        res, data = self.create(self.client, **obj_data)
        eq_(res.status_code, 400)
        ok_('name' in data)

    def test_create_invalid_type(self):
        self.feed_permission()
        obj_data = self.data(type='tuber')
        res, data = self.create(self.client, **obj_data)
        eq_(res.status_code, 400)
        ok_('type' in data)

    def test_create_no_description(self):
        self.feed_permission()
        obj_data = self.data()
        del obj_data['description']
        res, data = self.create(self.client, **obj_data)
        eq_(res.status_code, 201)

    def test_create_ungrouped(self):
        self.feed_permission()
        obj_data = self.data()
        obj_data['apps'] = self.ungrouped_apps()
        res, data = self.create(self.client, **obj_data)
        eq_(res.status_code, 201)
        for app in data['apps']:
            eq_(app['group'], None)

    def test_create_grouped(self):
        self.feed_permission()
        obj_data = self.data()
        obj_data['apps'] = self.grouped_apps()
        res, data = self.create(self.client, **obj_data)
        eq_(res.status_code, 201)
        self.assertGroupedAppsEqual(obj_data['apps'], data)

    def test_update_grouped(self):
        self.feed_permission()
        new_grouped = self.grouped_apps()
        res, data = self.update(self.client, apps=new_grouped)
        eq_(res.status_code, 200)
        self.assertGroupedAppsEqual(new_grouped, data)

    def test_update_no_background_image(self):
        self.feed_permission()
        self.obj_data['image_hash'] = 'LOL'
        res, data = self.update(self.client,
                                background_image_upload_url='')
        eq_(FeedCollection.objects.all()[0].image_hash, None)

    def test_get_with_apps(self):
        self.feed_permission()
        apps = [app.pk for app in self.make_apps()]
        data = dict(self.obj_data)
        data.update({'apps': apps})
        res, data = self.create(self.client, **data)

        res = self.client.get(reverse('api-v2:feedcollections-detail',
                                      args=[data['id']]))
        data = json.loads(res.content)
        self.assertSetEqual(
            apps, [app['id'] for app in data['apps']])

    @mock.patch('mkt.feed.views.pngcrush_image.delay')
    @mock.patch('mkt.feed.views.requests.get')
    def test_background_image(self, download_mock, crush_mock):
        """Tests with mocking the pngcrush."""
        res_mock = mock.Mock()
        res_mock.status_code = 200
        res_mock.content = open(
            os.path.join(FILES_DIR, 'bacon.jpg'), 'r').read()
        download_mock.return_value = res_mock

        self.feed_permission()
        data = dict(self.obj_data)
        data.update({'background_image_upload_url': 'ngokevin.com'})  # SEO.
        res, data = self.create(self.client, **data)

        coll = FeedCollection.objects.all()[0]
        eq_(coll.image_hash, 'e83ad266')
        ok_(data['background_image'].endswith(coll.image_hash))
        eq_(crush_mock.call_args_list[0][0][0], coll.image_path())
        eq_(crush_mock.call_args_list[0][1]['set_modified_on'][0], coll)

    @mock.patch('mkt.feed.views.requests.get')
    def test_background_image_404(self, download_mock):
        res_mock = mock.Mock()
        res_mock.status_code = 404
        res_mock.content = ''
        download_mock.return_value = res_mock

        self.feed_permission()
        data = dict(self.obj_data)
        data.update({'background_image_upload_url': 'ngokevin.com'})
        res, data = self.create(self.client, **data)

        eq_(res.status_code, 400)


class TestFeedShelfViewSet(BaseTestGroupedApps, BaseTestFeedCollection,
                           RestOAuth):
    obj_data = {
        'carrier': 'telefonica',
        'description': {'en-US': 'Potato french fries'},
        'region': 'br',
        'slug': 'potato',
        'name': {'en-US': 'Deep Fried'}
    }
    model = FeedShelf
    url_basename = 'feedshelves'

    def make_item(self):
        """
        Add additional unique fields: `description` and `name`.
        """
        super(TestFeedShelfViewSet, self).make_item(
            carrier=1, region=7, name={'en-US': 'Sprout'},
            description={'en-US': 'Baby Potato'})

    def setUp(self):
        super(TestFeedShelfViewSet, self).setUp()
        self.obj_data.update({
            'carrier': 'telefonica',
            'region': 'br'
        })

    def test_create_with_permission(self):
        self.feed_permission()
        res, data = self.create(self.client, **self.obj_data)
        eq_(res.status_code, 201)
        for name, value in self.obj_data.iteritems():
            eq_(value, data[name])

    def test_create_with_obj_permission(self):
        OperatorPermission.objects.create(
            carrier=mkt.carriers.TELEFONICA.id, region=mkt.regions.BRA.id,
            user=self.user)
        res, data = self.create(self.client, **self.obj_data)
        eq_(res.status_code, 201)
        for name, value in self.obj_data.iteritems():
            eq_(value, data[name])

    def test_create_ungrouped(self):
        self.feed_permission()
        obj_data = self.data()
        obj_data['apps'] = self.ungrouped_apps()
        res, data = self.create(self.client, **obj_data)
        eq_(res.status_code, 201)
        for app in data['apps']:
            eq_(app['group'], None)

    def test_create_grouped(self):
        self.feed_permission()
        obj_data = self.data()
        obj_data['apps'] = self.grouped_apps()
        res, data = self.create(self.client, **obj_data)
        eq_(res.status_code, 201)
        self.assertGroupedAppsEqual(obj_data['apps'], data)

    @mock.patch('mkt.feed.views.pngcrush_image.delay')
    @mock.patch('mkt.feed.views.requests.get')
    def test_create_with_multiple_images(self, download_mock, crush_mock):
        res_mock = mock.Mock()
        res_mock.status_code = 200
        res_mock.content = open(
            os.path.join(FILES_DIR, 'bacon.jpg'), 'r').read()
        download_mock.return_value = res_mock

        self.feed_permission()
        req_data = self.obj_data.copy()
        req_data.update(
            {'background_image_upload_url': 'ngokevin.com',
             'background_image_landing_upload_url': 'ngonekevin.com'})
        res, data = self.create(self.client, **req_data)

        obj = FeedShelf.objects.all()[0]
        ok_(data['background_image'].endswith(obj.image_hash))
        eq_(crush_mock.call_args_list[0][0][0], obj.image_path())
        ok_(data['background_image_landing'].endswith(obj.image_landing_hash))
        eq_(crush_mock.call_args_list[1][0][0], obj.image_path('_landing'))

    def test_delete_with_obj_permission(self):
        OperatorPermission.objects.create(
            carrier=mkt.carriers.TELEFONICA.id, region=mkt.regions.BRA.id,
            user=self.user)
        res, data = self.delete(self.client)
        eq_(res.status_code, 204)


class TestFeedShelfViewSetMine(FeedTestMixin, RestOAuth):
    fixtures = (FeedTestMixin.fixtures + RestOAuth.fixtures +
                fixture('user_999'))

    def setUp(self):
        super(TestFeedShelfViewSetMine, self).setUp()
        self.user2 = UserProfile.objects.get(id=999)
        self.url = reverse('api-v2:feedshelves-mine')
        self.feed_shelf_factory(
            carrier=mkt.carriers.TELEFONICA.id, region=mkt.regions.BRA.id)
        self.feed_shelf_factory(
            carrier=mkt.carriers.AMERICA_MOVIL.id, region=mkt.regions.FRA.id)

    def list(self, client):
        res = client.get(self.url)
        data = json.loads(res.content)
        eq_(res.status_code, 200)
        return res, data

    def test_anon(self):
        res, data = self.list(self.anon)
        eq_(len(data), 0)

    def test_superuser(self):
        self.grant_permission(self.user, 'OperatorDashboard:*')
        res, data = self.list(self.client)
        eq_(len(data), 2)

    def test_operator_permission(self):
        carrier = mkt.carriers.TELEFONICA
        region = mkt.regions.BRA
        self.feed_shelf_permission_factory(self.user, carrier=carrier.id,
                                           region=region.id)
        res, data = self.list(self.client)
        eq_(len(data), 1)
        eq_(data[0]['carrier'], carrier.slug)
        eq_(data[0]['region'], region.slug)

    def test_no_operator_permission(self):
        res, data = self.list(self.client)
        eq_(len(data), 0)


class TestBuilderView(FeedAppMixin, BaseTestFeedItemViewSet):
    fixtures = BaseTestFeedItemViewSet.fixtures + FeedAppMixin.fixtures

    def setUp(self):
        super(TestBuilderView, self).setUp()
        self.url = reverse('api-v2:feed.builder')
        self.profile = self.user

        self.feed_apps = self.create_feedapps(n=3)
        self.brand = FeedBrand.objects.create(slug='brandy')
        self.collection = FeedCollection.objects.create(slug='cull')
        self.data = {
            'us': [
                ['app', self.feed_apps[1].id],
                ['collection', self.collection.id],
                ['brand', self.brand.id],
                ['app', self.feed_apps[0].id],
            ],
            'cn': [
                ['brand', self.brand.id],
                ['app', self.feed_apps[2].id],
                ['collection', self.collection.id],
            ]
        }

    def _set_feed_items(self, data):
        return self.client.put(self.url, data=json.dumps(data))

    def test_create_feed(self):
        self.feed_permission()
        r = self._set_feed_items(self.data)
        eq_(r.status_code, 201)

        eq_(FeedItem.objects.count(), 7)
        us_items = FeedItem.objects.filter(
            region=mkt.regions.USA.id).order_by('order')
        eq_(us_items.count(), 4)

        # Test order.
        eq_(us_items[0].app_id, self.feed_apps[1].id)
        eq_(us_items[1].collection_id, self.collection.id)
        eq_(us_items[2].brand_id, self.brand.id)
        eq_(us_items[3].app_id, self.feed_apps[0].id)

        # Test item types.
        eq_(us_items[0].item_type, 'app')
        eq_(us_items[1].item_type, 'collection')
        eq_(us_items[2].item_type, 'brand')
        eq_(us_items[3].item_type, 'app')

        # Test China feed.
        cn_items = FeedItem.objects.filter(
            region=mkt.regions.CHN.id).order_by('order')
        eq_(cn_items.count(), 3)
        eq_(cn_items[0].item_type, 'brand')
        eq_(cn_items[1].item_type, 'app')
        eq_(cn_items[2].item_type, 'collection')

    def test_update_feed(self):
        self.feed_permission()
        self._set_feed_items(self.data)

        # Update US.
        self.data['us'] = self.data['cn']
        self._set_feed_items(self.data)

        us_items = FeedItem.objects.filter(
            region=mkt.regions.USA.id).order_by('order')
        eq_(us_items[0].brand_id, self.brand.id)
        eq_(us_items[1].app_id, self.feed_apps[2].id)

    def test_truncate_feed(self):
        """Fill up China feed, then send an empty array for China."""
        self.feed_permission()
        self._set_feed_items(self.data)
        ok_(FeedItem.objects.filter(region=mkt.regions.CHN.id))

        self.data['cn'] = []
        self._set_feed_items(self.data)
        ok_(FeedItem.objects.filter(region=mkt.regions.USA.id))
        ok_(not FeedItem.objects.filter(region=mkt.regions.CHN.id))

    def test_no_perm(self):
        """Fill up China feed, then send an empty array for China."""
        r = self._set_feed_items(self.data)
        eq_(r.status_code, 403)

    def test_cors(self):
        self.feed_permission()
        r = self._set_feed_items(self.data)
        self.assertCORS(r, 'put')

    def test_400(self):
        self.feed_permission()
        self.data['us'][0] = ['app']
        r = self._set_feed_items(self.data)
        eq_(r.status_code, 400)

    @mock.patch('mkt.search.indexers.BaseIndexer.index_ids')
    def test_index(self, index_mock):
        self.feed_permission()
        self._set_feed_items(self.data)
        ok_(index_mock.called)
        self.assertSetEqual(index_mock.call_args_list[0][0][0],
                            FeedItem.objects.values_list('id', flat=True))


class TestFeedElementSearchView(BaseTestFeedESView, BaseTestFeedItemViewSet):
    fixtures = BaseTestFeedItemViewSet.fixtures + FeedTestMixin.fixtures

    def setUp(self):
        super(TestFeedElementSearchView, self).setUp()

        self.app = self.feed_app_factory()
        self.brand = self.feed_brand_factory()
        self.collection = self.feed_collection_factory(name='Super Collection')
        self.shelf = self.feed_shelf_factory()
        self.feed_permission()
        self.url = reverse('api-v2:feed.element-search')
        self._refresh()

    def _search(self, q):
        res = self.client.get(self.url, data={'q': q or 'feed'})
        return res, json.loads(res.content)

    def test_query_slug(self):
        res, data = self._search('feed')
        eq_(res.status_code, 200)

        eq_(data['apps'][0]['id'], self.app.id)
        eq_(data['brands'][0]['id'], self.brand.id)
        eq_(data['collections'][0]['id'], self.collection.id)
        eq_(data['shelves'][0]['id'], self.shelf.id)

    def test_query_name(self):
        res, data = self._search('Super Collection')
        eq_(res.status_code, 200)

        eq_(data['collections'][0]['id'], self.collection.id)
        ok_(not data['apps'])
        ok_(not data['brands'])
        ok_(not data['shelves'])

    def test_query_type(self):
        res, data = self._search('mystery')
        eq_(res.status_code, 200)

        eq_(data['brands'][0]['id'], self.brand.id)
        ok_(not data['apps'])
        ok_(not data['collections'])
        ok_(not data['shelves'])

    def test_query_carrier(self):
        res, data = self._search('restofworld')
        eq_(res.status_code, 200)

        eq_(data['shelves'][0]['id'], self.shelf.id)
        ok_(not data['apps'])
        ok_(not data['brands'])
        ok_(not data['collections'])


class TestFeedShelfPublishView(BaseTestFeedItemViewSet,
                               mkt.site.tests.TestCase):
    fixtures = BaseTestFeedItemViewSet.fixtures + FeedTestMixin.fixtures

    def setUp(self):
        super(TestFeedShelfPublishView, self).setUp()
        self.shelf = self.feed_shelf_factory()
        self.url = reverse('api-v2:feed-shelf-publish', args=[self.shelf.id])

    def test_publish(self):
        self.feed_permission()
        res = self.client.put(self.url)
        data = json.loads(res.content)
        eq_(res.status_code, 201)

        eq_(data['carrier'],
            mkt.carriers.CARRIER_CHOICE_DICT[self.shelf.carrier].slug)
        eq_(data['region'],
            mkt.regions.REGIONS_CHOICES_ID_DICT[self.shelf.region].slug)
        eq_(data['shelf']['id'], self.shelf.id)

    def test_publish_anon(self):
        res = self.client.put(self.url)
        json.loads(res.content)
        eq_(res.status_code, 403)

    def test_publish_no_obj_permission(self):
        res = self.client.put(self.url)
        json.loads(res.content)
        eq_(res.status_code, 403)

    def test_publish_obj_permission(self):
        carrier = mkt.carriers.CARRIER_CHOICE_DICT[self.shelf.carrier]
        region = mkt.regions.REGIONS_CHOICES_ID_DICT[self.shelf.region]
        OperatorPermission.objects.create(user=self.user, region=region.id,
                                          carrier=carrier.id)
        res = self.client.put(self.url)
        json.loads(res.content)
        eq_(res.status_code, 201)

    def test_publish_overwrite(self):
        self.feed_permission()
        self.client.put(self.url)
        eq_(FeedItem.objects.count(), 1)
        ok_(FeedItem.objects.filter(shelf_id=self.shelf.id).exists())

        new_shelf = self.feed_shelf_factory()
        new_url = reverse('api-v2:feed-shelf-publish', args=[new_shelf.id])
        self.client.put(new_url)
        eq_(FeedItem.objects.count(), 1)
        ok_(FeedItem.objects.filter(shelf_id=new_shelf.id).exists())

    def test_unpublish(self):
        self.feed_permission()
        # Publish.
        self.client.put(self.url)
        eq_(FeedItem.objects.count(), 1)
        ok_(FeedItem.objects.filter(shelf_id=self.shelf.id).exists())

        # Unpublish.
        res = self.client.delete(self.url)
        eq_(FeedItem.objects.count(), 0)
        eq_(res.status_code, 204)

    def test_404(self):
        self.feed_permission()
        self.url = reverse('api-v2:feed-shelf-publish', args=[8008135])
        res = self.client.put(self.url)
        eq_(res.status_code, 404)

        res = self.client.delete(self.url)
        eq_(res.status_code, 404)


class TestFeedView(BaseTestFeedESView, BaseTestFeedItemViewSet):
    fixtures = BaseTestFeedItemViewSet.fixtures + FeedTestMixin.fixtures

    def setUp(self):
        super(TestFeedView, self).setUp()
        self.url = reverse('api-v2:feed.get')
        self.carrier = 'telefonica'
        self.region = 'restofworld'

    def _make_website(self, tag=None):
        new_site = website_factory(**{
            'title': 'something',
            'categories': [],
        })
        if tag:
            new_site.keywords.add(tag)
        return new_site

    def featured_mow_factory(self, n_row=0, n_www=0):
        websites = []
        www = Tag.objects.get_or_create(tag_text='featured-website')[0]
        for n in xrange(n_www):
            websites.append(self._make_website(tag=www.pk))
        row = Tag.objects.get_or_create(
            tag_text='featured-website-restofworld')[0]
        for n in xrange(n_row):
            websites.append(self._make_website(tag=row.pk))
        self.reindex(Website)
        return websites

    def _get(self, client=None, **kwargs):
        self._refresh()
        client = client or self.anon
        kwargs['carrier'] = kwargs.get('carrier', self.carrier)
        kwargs['region'] = kwargs.get('region', self.region)

        if kwargs.get('no_assert_queries'):
            # For auth tests, where a bunch of user-related queries are dne.
            res = client.get(self.url, kwargs)
        else:
            with self.assertNumQueries(0):
                res = client.get(self.url, kwargs)
        data = json.loads(res.content) if res.content else {}
        return res, data

    @mock.patch('mkt.feed.views.statsd.timer')
    def test_200(self, statsd_mock):
        feed_items = self.feed_factory()
        res, data = self._get()
        eq_(res.status_code, 200)
        eq_(len(data['objects']), len(feed_items))
        eq_(len(data['websites']), 0)
        ok_(statsd_mock.called)
        return res, data

    def test_200_authed(self):
        feed_items = self.feed_factory()
        res, data = self._get(self.client, no_assert_queries=True)
        eq_(res.status_code, 200)
        eq_(len(data['objects']), len(feed_items))

    def test_404(self):
        res, data = self._get(self.client, no_assert_queries=True)
        eq_(res.status_code, 404)

    def test_region_only(self):
        feed_items = self.feed_factory()
        res, data = self._get(carrier=None)
        eq_(len(data['objects']), len(feed_items) - 1)  # No shelf.

    def test_carrier_only(self):
        feed_items = self.feed_factory()
        res, data = self._get(region=None)
        eq_(len(data['objects']), len(feed_items))

    def test_feed_app_only(self):
        self.feed_item_factory()
        res, data = self._get()
        eq_(len(data['objects']), 1)

    def test_shelf_top(self):
        self.feed_factory()
        res, data = self._get()
        eq_(data['objects'][0]['item_type'],
            feed.FEED_TYPE_SHELF)

    def test_websites(self):
        self.feed_factory()
        self.featured_mow_factory(n_row=6, n_www=5)
        res, data = self._get()
        tags = [mow['keywords'][0] for mow in data['websites']]
        eq_(len(data['websites']), 11)
        eq_(tags.count('featured-website-restofworld'), 6)
        eq_(tags.count('featured-website'), 5)

    def test_websites_prefer_regional(self):
        """
        Ensure that all regionally featured websites are returned before any
        globally-featured websites are considered.
        """
        self.feed_factory()
        self.featured_mow_factory(n_row=11, n_www=1)
        res, data = self._get()
        tags = [mow['keywords'][0] for mow in data['websites']]
        eq_(len(data['websites']), 11)
        eq_(tags.count('featured-website-restofworld'), 11)
        eq_(tags.count('featured-website'), 0)

    def test_websites_random_seed(self):
        """
        Ensure that consecutive queries don't return different random
        selections.
        """
        self.feed_factory()
        self.featured_mow_factory(n_row=5, n_www=10)
        res1, data1 = self._get()
        res2, data2 = self._get()
        eq_(data1['websites'], data2['websites'])

    @mock.patch('mkt.feed.views.FeedView._get_daily_seed')
    def test_websites_daily_change(self, mock_daily_seed):
        """
        Ensure that queries from different days return different random
        selections.
        """
        self.feed_factory()
        self.featured_mow_factory(n_row=5, n_www=10)
        mock_daily_seed.return_value = 20150101
        res1, data1 = self._get()
        mock_daily_seed.return_value = 20150102
        res2, data2 = self._get()
        ok_(data1['websites'] != data2['websites'])

    @mock.patch('mkt.api.paginator.CustomPagination.get_limit')
    def test_limit_honored(self, get_limit):
        PAGINATE_BY = 3
        TOTAL = PAGINATE_BY + 1
        get_limit.return_value = PAGINATE_BY

        self.feed_factory(num_items=TOTAL)
        res, data = self._get(limit=PAGINATE_BY, offset=0)

        eq_(data['meta']['total_count'], TOTAL)
        eq_(data['meta']['limit'], PAGINATE_BY)
        ok_(not data['meta']['previous'])
        ok_(data['meta']['next'])
        eq_(len(data['objects']), PAGINATE_BY)

    @mock.patch('mkt.api.paginator.CustomPagination.get_limit')
    def test_offset_honored(self, get_limit):
        PAGINATE_BY = 3
        TOTAL = PAGINATE_BY * 2 + 1  # Three pages.
        get_limit.return_value = TOTAL

        self.feed_factory(num_items=TOTAL)

        res_all, data_all = self._get()
        get_limit.return_value = PAGINATE_BY
        res, data = self._get(offset=PAGINATE_BY)

        eq_(data['meta']['total_count'], TOTAL)
        eq_(data['meta']['limit'], PAGINATE_BY)
        eq_(data['meta']['offset'], PAGINATE_BY)
        eq_(len(data['objects']), PAGINATE_BY)
        ok_(data['meta']['previous'])
        ok_(data['meta']['next'])
        eq_(data_all['objects'][PAGINATE_BY], data['objects'][0])

    @mock.patch('mkt.api.paginator.PageNumberPagination.get_page_size')
    def test_page_honored(self, get_page_size):
        PAGINATE_BY = 3
        TOTAL = PAGINATE_BY + 1
        get_page_size.return_value = TOTAL
        self.feed_factory(num_items=TOTAL)

        res_all, data_all = self._get()
        get_page_size.return_value = PAGINATE_BY
        res, data = self._get(page=2)

        ok_(data['meta']['previous'])
        ok_(not data['meta']['next'])
        eq_(data_all['objects'][-1], data['objects'][0])

    def test_region_filter(self):
        """Test that changing region gives different feed."""
        self.feed_factory()
        self.feed_item_factory(region=2)
        res, data = self._get(region='us')
        eq_(len(data['objects']), 1)

    def test_carrier_filter(self):
        """Test that changing carrier affects the opshelf."""
        self.feed_factory()
        res, data = self._get(carrier='tmn')
        eq_(len(data['objects']), 3)
        ok_(data['objects'][0]['item_type'] != feed.FEED_TYPE_SHELF)

    def test_deserialized(self):
        """Test that feed elements and apps are deserialized."""
        self.feed_factory()
        res, data = self._get()
        for feed_item in data['objects']:
            item_type = feed_item['item_type']
            feed_elm = feed_item[item_type]
            if feed_elm.get('app'):
                ok_(feed_elm['app']['id'])
            else:
                if feed_item['item_type'] == feed.FEED_TYPE_SHELF:
                    # Shelves don't display app data on feed.
                    continue
                ok_(len(feed_elm['apps']))
                for app in feed_elm['apps']:
                    ok_(app['id'])

    def test_restofworld_fallback(self):
        feed_items = self.feed_factory()
        res, data = self._get(region='us')
        eq_(len(data['objects']), len(feed_items))

    def test_restofworld_fallback_shelf_only(self):
        shelf = self.feed_shelf_factory()
        shelf.feeditem_set.create(region=mkt.regions.USA.id,
                                  carrier=mkt.carriers.AMERICA_MOVIL.id,
                                  item_type=feed.FEED_TYPE_SHELF)

        feed_items = self.feed_factory()
        res, data = self._get(region='us', carrier='america_movil')
        eq_(len(data['objects']), len(feed_items))

        # Keep the shelf, you filthy animal.
        eq_(data['objects'][0]['item_type'], 'shelf')
        eq_(data['objects'][0]['shelf']['id'], shelf.id)

    def test_shelf_only_404(self):
        shelf = self.feed_shelf_factory()
        shelf.feeditem_set.create(region=mkt.regions.USA.id,
                                  item_type=feed.FEED_TYPE_SHELF)
        res, data = self._get()
        eq_(res.status_code, 404)

    def test_order(self):
        """Test feed elements are ordered by their order attribute."""
        feed_items = [self.feed_item_factory(order=i + 1) for i in xrange(4)]
        res, data = self._get()
        for i, feed_item in enumerate(feed_items):
            eq_(data['objects'][i]['id'], feed_item.id)

    @mock.patch.object(mkt.feed.constants, 'MIN_APPS_COLLECTION', 3)
    def test_collection_min_apps(self):
        """Test collections must have minimum number of apps to be public."""
        app_ids = [app_factory().id, app_factory().id]
        coll = self.feed_collection_factory(app_ids=app_ids)
        FeedItem.objects.create(collection=coll, item_type=feed.FEED_TYPE_COLL,
                                region=1)
        res, data = self._get()
        eq_(res.status_code, 404)

        app_ids.append(app_factory().id)
        coll.set_apps(app_ids)
        coll.get_indexer().index_ids([coll.id])
        res, data = self._get()
        eq_(res.status_code, 200)
        ok_(data['objects'])

    def test_collection_promo_background_image(self):
        # Create the feed collection, a promo with a background image.
        app_ids = [app_factory().id for i in range(3)]
        coll = self.feed_collection_factory(app_ids=app_ids,
                                            coll_type=feed.COLLECTION_PROMO,
                                            image_hash='abcdefgh')
        item = FeedItem.objects.create(collection=coll,
                                       item_type=feed.FEED_TYPE_COLL, region=1)

        # Get the feed for which the feed item should be a member.
        res, data = self._get(filtering=0)
        eq_(res.status_code, 200)
        eq_(data['objects'][0]['id'], item.id)
        ok_(len(data['objects'][0]['collection']['apps']))

    @mock.patch.object(mkt.feed.constants, 'MIN_APPS_COLLECTION', 3)
    def test_brand_no_min_apps(self):
        """Test brands have no minimum enforcement on number of apps."""
        app_ids = [app_factory().id]
        brand = self.feed_brand_factory(app_ids=app_ids)
        FeedItem.objects.create(brand=brand, item_type=feed.FEED_TYPE_BRAND,
                                region=1)
        res, data = self._get()
        ok_(data['objects'])

    def test_groups(self):
        """Test feed collection app groups."""
        coll = self.feed_collection_factory(grouped=True)
        FeedItem.objects.create(collection=coll, item_type=feed.FEED_TYPE_COLL,
                                region=1)
        res, data = self._get()
        eq_(data['objects'][0]['collection']['apps'][0]['group'],
            {'en-US': 'first-group'})

    def test_fallback_if_apps_filtered(self):
        # Create fallback item.
        coll = self.feed_collection_factory(
            app_ids=[mkt.site.tests.app_factory().id])
        FeedItem.objects.create(collection=coll, item_type=feed.FEED_TYPE_COLL,
                                region=1)

        feed_item = self.feed_item_factory(item_type=feed.FEED_TYPE_APP)
        app = feed_item.app.app
        app.update(disabled_by_user=True)
        res, data = self._get()
        eq_(res.status_code, 200)

    def test_many_apps(self):
        for x in range(4):
            coll = self.feed_collection_factory(
                app_ids=[mkt.site.tests.app_factory().id for x in range(3)])
            FeedItem.objects.create(collection=coll,
                                    item_type=feed.FEED_TYPE_COLL, region=1)

        res, data = self._get(region=1)
        eq_(res.status_code, 200)
        for obj in data['objects']:
            eq_(obj['collection']['app_count'], 3)

        res, data = self._get(region=1, filtering=0)
        eq_(res.status_code, 200)
        for obj in data['objects']:
            eq_(obj['collection']['app_count'], 3)

    def test_no_carrier_no_shelf(self):
        # Test a shelf only shows if a carrier is passed.
        self.feed_item_factory(item_type=feed.FEED_TYPE_APP)
        self.feed_item_factory(item_type=feed.FEED_TYPE_SHELF)
        res, data = self._get(region=1, carrier=None)
        eq_(res.status_code, 200)
        eq_(len(data['objects']), 1)

    def test_q_num_requests(self):
        self.feed_factory()
        es = FeedItem.get_indexer().get_es()
        orig_search = es.search
        es.counter = 0

        def monkey_search(*args, **kwargs):
            es.counter += 1
            return orig_search(*args, **kwargs)

        es.search = monkey_search

        res, data = self._get()
        eq_(res.status_code, 200)
        eq_(res.json['meta']['total_count'], 4)
        eq_(len(res.json['objects']), 4)

        # FeedView._get does four ES hits: feed items, feed elements, apps, and
        # featured websites.
        eq_(es.counter, 4)

        es.search = orig_search


class TestFeedViewDeviceFiltering(BaseTestFeedESView, BaseTestFeedItemViewSet):
    fixtures = BaseTestFeedItemViewSet.fixtures + FeedTestMixin.fixtures

    def setUp(self):
        super(TestFeedViewDeviceFiltering, self).setUp()
        self.url = reverse('api-v2:feed.get')

    def _get(self, **kwargs):
        self._refresh()
        res = self.anon.get(self.url, kwargs)
        data = json.loads(res.content) if res.content else {}
        return res, data

    def test_feedapp(self):
        feed_item = self.feed_item_factory(item_type=feed.FEED_TYPE_APP)
        feed_item.app.app.addondevicetype_set.create(
            device_type=applications.DEVICE_DESKTOP.id)

        # Mobile doesn't show desktop apps.
        res, data = self._get(device='firefoxos', dev='firefoxos')
        eq_(res.status_code, 404)
        res, data = self._get(device='mobile', dev='android')
        eq_(res.status_code, 404)
        res, data = self._get(device='tablet', dev='android')
        eq_(res.status_code, 404)

        # Desktop shows desktop apps.
        res, data = self._get(dev='desktop')
        ok_(data['objects'])

    def test_coll(self):
        # Longest set up ever. Create apps for different devices.
        app_gaia = mkt.site.tests.app_factory()
        app_android = mkt.site.tests.app_factory()
        app_desktop = mkt.site.tests.app_factory()
        app_gaia.addondevicetype_set.create(
            device_type=applications.DEVICE_GAIA.id)
        app_android.addondevicetype_set.create(
            device_type=applications.DEVICE_MOBILE.id)
        app_desktop.addondevicetype_set.create(
            device_type=applications.DEVICE_DESKTOP.id)

        # Create coll containing apps for different devices.
        coll = self.feed_collection_factory(
            app_ids=[app_gaia.id, app_android.id, app_desktop.id])

        # Wrap in FeedItem.
        FeedItem.objects.create(item_type=feed.FEED_TYPE_COLL,
                                collection=coll, region=1)

        # No filtering.
        res, data = self._get()
        eq_(len(data['objects']), 1)
        eq_(data['objects'][0]['collection']['app_count'], 3)

        # Only FirefoxOS compatible apps.
        res, data = self._get(device='firefoxos', dev='firefoxos')
        eq_(len(data['objects']), 1)
        eq_(data['objects'][0]['collection']['apps'][0]['id'], app_gaia.id)
        eq_(data['objects'][0]['collection']['app_count'], 1)

        # Only Android mobile compatible apps.
        res, data = self._get(device='mobile', dev='android')
        eq_(len(data['objects']), 1)
        eq_(data['objects'][0]['collection']['apps'][0]['id'], app_android.id)
        eq_(data['objects'][0]['collection']['app_count'], 1)

        # Only Desktop compatible apps.
        res, data = self._get(dev='desktop')
        eq_(len(data['objects']), 1)
        eq_(data['objects'][0]['collection']['apps'][0]['id'], app_desktop.id)
        eq_(data['objects'][0]['collection']['app_count'], 1)

    def test_multiple_device_types(self):
        feed_item = self.feed_item_factory(item_type=feed.FEED_TYPE_APP)
        feed_item.app.app.addondevicetype_set.create(
            device_type=applications.DEVICE_DESKTOP.id)
        feed_item.app.app.addondevicetype_set.create(
            device_type=applications.DEVICE_GAIA.id)

        # Shows up on Desktop and Gaia.
        res, data = self._get(dev='desktop')
        ok_(data['objects'])
        res, data = self._get(device='firefoxos', dev='firefoxos')
        ok_(data['objects'])

        # Does not shows up on Android.
        res, data = self._get(device='tablet', dev='android')
        eq_(res.status_code, 404)

    def test_bad_device_type(self):
        self.feed_item_factory(item_type=feed.FEED_TYPE_APP)
        res, data = self._get(dev='wut')
        ok_(data['objects'])

    def test_no_filtering(self):
        app_gaia = mkt.site.tests.app_factory()
        app_gaia.addondevicetype_set.create(
            device_type=applications.DEVICE_GAIA.id)
        coll = self.feed_collection_factory(app_ids=[app_gaia.id])
        FeedItem.objects.create(item_type=feed.FEED_TYPE_COLL, collection=coll,
                                region=1)

        res, data = self._get(device='mobile', dev='android')
        eq_(res.status_code, 404)

        res, data = self._get(device='mobile', dev='android', filtering=0)
        eq_(len(data['objects']), 1)


class TestFeedViewRegionFiltering(BaseTestFeedESView, BaseTestFeedItemViewSet):
    fixtures = BaseTestFeedItemViewSet.fixtures + FeedTestMixin.fixtures

    def setUp(self):
        super(TestFeedViewRegionFiltering, self).setUp()
        self.url = reverse('api-v2:feed.get')

    def _get(self, **kwargs):
        self._refresh()
        res = self.anon.get(self.url, kwargs)
        data = json.loads(res.content) if res.content else {}
        return res, data

    def test_feedapp(self):
        feed_item = self.feed_item_factory(item_type=feed.FEED_TYPE_APP)
        app = feed_item.app.app
        # Exclude from Germany.
        app.addonexcludedregion.create(region=mkt.regions.DEU.id)
        res, data = self._get()
        ok_(data['objects'])
        res, data = self._get(region='de')
        eq_(res.status_code, 404)

        res, data = self._get(region='us')
        ok_(data['objects'])

    def test_coll(self):
        app_excluded_br = mkt.site.tests.app_factory()
        app_excluded_de = mkt.site.tests.app_factory()
        app_excluded_br.addonexcludedregion.create(region=mkt.regions.BRA.id)
        app_excluded_de.addonexcludedregion.create(region=mkt.regions.DEU.id)
        coll = self.feed_collection_factory(app_ids=[app_excluded_br.id,
                                                     app_excluded_de.id])

        # Wrap in FeedItem.
        FeedItem.objects.create(item_type=feed.FEED_TYPE_COLL, collection=coll,
                                region=1)

        # Other regions can see both.
        res, data = self._get(region='restofworld')
        eq_(len(data['objects'][0]['collection']['apps']), 2)

        # Test DE exclusion.
        res, data = self._get(region='de')
        eq_(len(data['objects'][0]['collection']['apps']), 1)
        eq_(data['objects'][0]['collection']['apps'][0]['id'],
            app_excluded_br.id)

        # Test BR exclusion.
        res, data = self._get(region='br')
        eq_(len(data['objects'][0]['collection']['apps']), 1)
        eq_(data['objects'][0]['collection']['apps'][0]['id'],
            app_excluded_de.id)

    def test_no_filtering(self):
        app_excluded_br = mkt.site.tests.app_factory()
        app_excluded_br.addonexcludedregion.create(region=mkt.regions.BRA.id)
        coll = self.feed_collection_factory(app_ids=[app_excluded_br.id])
        FeedItem.objects.create(item_type=feed.FEED_TYPE_COLL, collection=coll,
                                region=1)

        res, data = self._get(region='br')
        eq_(res.status_code, 404)

        res, data = self._get(region='br', filtering=0)
        eq_(len(data['objects']), 1)


class TestFeedViewStatusFiltering(BaseTestFeedESView, BaseTestFeedItemViewSet):
    fixtures = BaseTestFeedItemViewSet.fixtures + FeedTestMixin.fixtures

    def setUp(self):
        super(TestFeedViewStatusFiltering, self).setUp()
        self.url = reverse('api-v2:feed.get')

    def _get(self, **kwargs):
        self._refresh()
        res = self.anon.get(self.url, kwargs)
        data = json.loads(res.content) if res.content else {}
        return res, data

    def test_feedapp(self):
        feed_item = self.feed_item_factory(item_type=feed.FEED_TYPE_APP)
        app = feed_item.app.app
        app.update(status=mkt.STATUS_PENDING)
        res, data = self._get()
        eq_(res.status_code, 404)

    def test_coll(self):
        app_pending = app_factory(status=mkt.STATUS_PENDING)
        app_public = app_factory(status=mkt.STATUS_PUBLIC)

        coll = self.feed_collection_factory(
            app_ids=[app_pending.id, app_public.id])

        # Wrap in FeedItem.
        FeedItem.objects.create(item_type=feed.FEED_TYPE_COLL,
                                collection=coll, region=1)

        res, data = self._get()
        eq_(len(data['objects']), 1)
        eq_(data['objects'][0]['collection']['apps'][0]['id'], app_public.id)

    def test_is_disabled(self):
        feed_item = self.feed_item_factory(item_type=feed.FEED_TYPE_APP)
        app = feed_item.app.app
        app.update(disabled_by_user=True)
        res, data = self._get()
        eq_(res.status_code, 404)


class TestFeedViewQueries(BaseTestFeedItemViewSet, TestCase):
    fixtures = BaseTestFeedItemViewSet.fixtures + FeedTestMixin.fixtures

    def setUp(self):
        self.fv = FeedView()
        self.sq = Search()

    def test_region_default(self):
        """Region default to RoW."""
        sq = self.fv.get_es_feed_query(self.sq).to_dict()
        eq_(sq['query']['function_score']['filter']['bool']['must'][0]['term']
              ['region'], 1)

    def test_region(self):
        """With region only."""
        sq = self.fv.get_es_feed_query(self.sq, region=2).to_dict()
        eq_(sq['query']['function_score']['filter']['bool']['must'][0]['term']
              ['region'], 2)

    def test_carrier_with_region(self):
        sq = self.fv.get_es_feed_query(self.sq, region=2, carrier=1).to_dict()
        # Test filter.
        ok_({'term': {'region': 2}}
            in sq['query']['function_score']['filter']['bool']['should'])
        ok_({'bool': {'must_not': [{'term': {'carrier': 1}}],
                      'must': [{'term': {'item_type': 'shelf'}}]}}
            in sq['query']['function_score']['filter']['bool']['must_not'])
        # Test functions.
        ok_({'filter': {'term': {'item_type': 'shelf'}},
             'boost_factor': 10000.0}
            in sq['query']['function_score']['functions'])
        ok_({'filter': {'bool': {
            'must_not': [{'term': {'item_type': 'shelf'}}],
            'must': [{'term': {'region': 2}}]}},
            'field_value_factor': {'field': 'order',
                                   'modifier': 'reciprocal'}}
            in sq['query']['function_score']['functions'])

    def test_carrier_default_region(self):
        sq = self.fv.get_es_feed_query(self.sq, carrier=1).to_dict()
        # Test filter.
        ok_({'term': {'region': 1}}
            in sq['query']['function_score']['filter']['bool']['should'])

    def test_order(self):
        """Order script scoring."""
        sq = self.fv.get_es_feed_query(self.sq).to_dict()
        ok_({'term': {'region': 1}}
            in sq['query']['function_score']['functions'][0]
            ['filter']['bool']['must'])
        ok_({'term': {'item_type': 'shelf'}}
            in sq['query']['function_score']['functions'][0]
            ['filter']['bool']['must_not'])
        eq_(sq['query']['function_score']['functions'][0]
            ['field_value_factor'], {'field': 'order',
                                     'modifier': 'reciprocal'})

    def test_element_query(self):
        feed_item = self.feed_item_factory()
        item = feed_item.get_indexer().extract_document(None, obj=feed_item)
        sq = self.fv.get_es_feed_element_query(self.sq, [item]).to_dict()
        ok_({'bool': {'must': [{'term': {'id': feed_item.app_id}},
                               {'term': {'item_type': 'app'}}]}}
            in sq['query']['filtered']['filter']['bool']['should'])
        eq_(sq['from'], 0)
        eq_(sq['size'], 1)


class TestFeedElementGetView(BaseTestFeedESView, BaseTestFeedItemViewSet):
    fixtures = BaseTestFeedItemViewSet.fixtures + FeedTestMixin.fixtures

    def _get(self, url, **kwargs):
        self._refresh()
        with self.assertNumQueries(0):
            res = self.anon.get(url, kwargs)
        data = json.loads(res.content) if res.content else {}
        return res, data

    def _assert(self, obj, result):
        eq_(obj.id, result['id'])
        if hasattr(obj, 'app_id'):
            eq_(obj.app_id, result['app']['id'])
        else:
            self.assertSetEqual(
                obj.apps().values_list('id', flat=True),
                [app['id'] for app in result['apps']])

    def test_app(self):
        app = self.feed_app_factory()
        url = reverse('api-v2:feed.feed_element_get',
                      args=['apps', app.slug])
        res, data = self._get(url)
        self._assert(app, data)

        url = reverse('api-v2:feed.fire_feed_element_get',
                      args=['apps', app.slug])
        res, data = self._get(url)
        self._assert(app, data)
        assert_fireplace_app(data['app'])

        url = reverse('api-v2:feed.feed_element_get',
                      args=['apps', app.slug])
        res, data = self._get(url, app_serializer='fireplace',
                              region='restofworld')
        self._assert(app, data)
        assert_fireplace_app(data['app'])

        self._assert(app, data)

    def test_brand(self):
        brand = self.feed_brand_factory()
        url = reverse('api-v2:feed.feed_element_get',
                      args=['brands', brand.slug])
        res, data = self._get(url)
        self._assert(brand, data)

        url = reverse('api-v2:feed.fire_feed_element_get',
                      args=['brands', brand.slug])
        res, data = self._get(url)
        self._assert(brand, data)
        assert_fireplace_app(data['apps'][0])

        url = reverse('api-v2:feed.feed_element_get',
                      args=['brands', brand.slug])
        res, data = self._get(url, app_serializer='fireplace')
        self._assert(brand, data)
        assert_fireplace_app(data['apps'][0])

    def test_collection(self):
        collection = self.feed_collection_factory()
        url = reverse('api-v2:feed.feed_element_get',
                      args=['collections', collection.slug])
        res, data = self._get(url)
        self._assert(collection, data)

        url = reverse('api-v2:feed.fire_feed_element_get',
                      args=['collections', collection.slug])
        res, data = self._get(url)
        self._assert(collection, data)
        assert_fireplace_app(data['apps'][0])

        url = reverse('api-v2:feed.feed_element_get',
                      args=['collections', collection.slug])
        res, data = self._get(url, app_serializer='fireplace')
        self._assert(collection, data)
        assert_fireplace_app(data['apps'][0])

    def test_shelf(self):
        shelf = self.feed_shelf_factory()
        url = reverse('api-v2:feed.feed_element_get',
                      args=['shelves', shelf.slug])
        res, data = self._get(url)
        self._assert(shelf, data)

        url = reverse('api-v2:feed.fire_feed_element_get',
                      args=['shelves', shelf.slug])
        res, data = self._get(url)
        self._assert(shelf, data)
        assert_fireplace_app(data['apps'][0])

        url = reverse('api-v2:feed.feed_element_get',
                      args=['shelves', shelf.slug])
        res, data = self._get(url, app_serializer='fireplace')
        self._assert(shelf, data)
        assert_fireplace_app(data['apps'][0])

    def test_404(self):
        url = reverse('api-v2:feed.feed_element_get',
                      args=['shelves', 'tehshrike'])
        res = self.anon.get(url)
        eq_(res.status_code, 404)

    def test_device_filtering(self):
        app_gaia = mkt.site.tests.app_factory()
        app_android = mkt.site.tests.app_factory()
        app_desktop = mkt.site.tests.app_factory()
        app_gaia.addondevicetype_set.create(
            device_type=applications.DEVICE_GAIA.id)
        app_android.addondevicetype_set.create(
            device_type=applications.DEVICE_MOBILE.id)
        app_desktop.addondevicetype_set.create(
            device_type=applications.DEVICE_DESKTOP.id)

        # Create coll containing apps for different devices.
        coll = self.feed_collection_factory(
            app_ids=[app_gaia.id, app_android.id, app_desktop.id])
        url = reverse('api-v2:feed.feed_element_get',
                      args=['collections', coll.slug])

        res, data = self._get(url, device='firefoxos', dev='firefoxos')
        eq_(len(data['apps']), 1)
        eq_(data['apps'][0]['id'], app_gaia.id)

        res, data = self._get(url, device='mobile', dev='android')
        eq_(len(data['apps']), 1)
        eq_(data['apps'][0]['id'], app_android.id)

        res, data = self._get(url, dev='desktop')
        eq_(len(data['apps']), 1)
        eq_(data['apps'][0]['id'], app_desktop.id)


class TestFeedElementListView(BaseTestFeedESView, BaseTestFeedItemViewSet):
    fixtures = BaseTestFeedItemViewSet.fixtures + FeedTestMixin.fixtures

    def setUp(self):
        super(TestFeedElementListView, self).setUp()
        self.feed_permission()

    def _get(self, url, data=None, **kwargs):
        self._refresh()
        res = self.client.get(url, data=data)
        data = json.loads(res.content)
        return res, data

    def test_404(self):
        res, data = self._get(reverse('api-v2:feed.feed_element_list',
                                      args=['apps']))
        eq_(res.status_code, 404)
        eq_(data['objects'], [])

    def test_apps(self):
        n = 5
        apps = [self.feed_app_factory() for i in range(n)]
        [apps[i].update(created=self.days_ago(i)) for i in reversed(range(n))]

        res, data = self._get(reverse('api-v2:feed.feed_element_list',
                                      args=['apps']))
        eq_(res.status_code, 200)
        eq_(data['meta']['total_count'], 5)
        [eq_(data['objects'][i]['id'], apps[i].id) for i in range(n)]

    def test_paginate(self):
        n = 6
        brands = [self.feed_brand_factory() for i in range(n)]
        [brands[i].update(created=self.days_ago(i)) for i in
         reversed(range(n))]

        # Offset only.
        res, data = self._get(reverse('api-v2:feed.feed_element_list',
                                      args=['brands']),
                              data={'limit': 5, 'offset': 5})
        eq_(data['meta']['total_count'], 6)
        eq_(data['meta']['limit'], 5)
        eq_(len(data['objects']), 1)
        eq_(data['objects'][0]['id'], brands[n - 1].id)

        # Offset and limit.
        res, data = self._get(reverse('api-v2:feed.feed_element_list',
                                      args=['brands']),
                              data={'limit': 1, 'offset': 1})
        eq_(data['meta']['total_count'], 6)
        eq_(data['meta']['limit'], 1)
        eq_(len(data['objects']), 1)
        eq_(data['objects'][0]['id'], brands[1].id)
