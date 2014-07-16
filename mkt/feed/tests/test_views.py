# -*- coding: utf-8 -*-
import json

from django.core.urlresolvers import reverse
from django.utils.text import slugify

from nose.tools import eq_, ok_

import amo.tests
from amo.tests import app_factory

import mkt.carriers
import mkt.regions
from mkt.api.tests.test_oauth import RestOAuth
from mkt.constants.carriers import CARRIER_MAP
from mkt.constants.regions import REGIONS_DICT
from mkt.feed.models import (FeedApp, FeedBrand, FeedCollection, FeedItem,
                             FeedShelf)
from mkt.feed.tests.test_models import FeedAppMixin, FeedTestMixin
from mkt.site.fixtures import fixture
from mkt.webapps.models import Preview, Webapp


class BaseTestFeedItemViewSet(RestOAuth, FeedTestMixin):
    def setUp(self):
        super(BaseTestFeedItemViewSet, self).setUp()
        self.profile = self.user

    def feed_permission(self):
        """
        Grant the Feed:Curate permission to the authenticating user.
        """
        self.grant_permission(self.profile, 'Feed:Curate')


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
                                carrier=mkt.carriers.TELEFONICA.id,
                                region=mkt.regions.BR.id)
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
        res, data = self.update(self.client, region=mkt.regions.US.id)
        eq_(res.status_code, 200)
        eq_(data['id'], self.item.pk)
        eq_(data['region'], mkt.regions.US.slug)

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

    def test_create_with_background_color(self):
        self.feedapp_data.update(background_color='#00AACC')
        res, data = self.test_create_with_permission()
        eq_(data['background_color'], '#00AACC')

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
        ok_('__all__' in data)

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
        assert data.get('background_image')


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
        eq_(res1.status_code, 201)
        eq_(obj_data['slug'], data1['slug'])

        res2, data2 = self.create(self.client, **obj_data)
        eq_(res2.status_code, 400)
        ok_('slug' in data2)

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


class TestFeedCollectionViewSet(BaseTestFeedCollection, RestOAuth):
    obj_data = {
        'slug': 'potato',
        'type': 'promo',
        'background_color': '#00AACC',
        'description': {'en-US': 'Potato french fries'},
        'name': {'en-US': 'Deep Fried'}
    }
    model = FeedCollection
    url_basename = 'feedcollections'

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


class TestFeedShelfViewSet(BaseTestFeedCollection, RestOAuth):
    obj_data = {
        'background_color': '#00AACC',
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
            region=mkt.regions.US.id).order_by('order')
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
            region=mkt.regions.CN.id).order_by('order')
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
            region=mkt.regions.US.id).order_by('order')
        eq_(us_items[0].brand_id, self.brand.id)
        eq_(us_items[1].app_id, self.feed_apps[2].id)

    def test_truncate_feed(self):
        """Fill up China feed, then send an empty array for China."""
        self.feed_permission()
        self._set_feed_items(self.data)
        ok_(FeedItem.objects.filter(region=mkt.regions.CN.id))

        self.data['cn'] = []
        self._set_feed_items(self.data)
        ok_(FeedItem.objects.filter(region=mkt.regions.US.id))
        ok_(not FeedItem.objects.filter(region=mkt.regions.CN.id))

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


class TestFeedElementSearchView(BaseTestFeedItemViewSet, amo.tests.ESTestCase):
    fixtures = BaseTestFeedItemViewSet.fixtures + FeedTestMixin.fixtures

    def setUp(self):
        super(TestFeedElementSearchView, self).setUp()
        self.setUpIndex()

        self.app = self.feed_app_factory()
        self.brand = self.feed_brand_factory()
        self.collection = self.feed_collection_factory(name='Super Collection')
        self.shelf = self.feed_shelf_factory()
        self.feed_permission()
        self.url = reverse('api-v2:feed.element-search')

        self._refresh_feed_es()

    def _refresh_feed_es(self):
        self.refresh(FeedApp._meta.db_table)
        self.refresh(FeedBrand._meta.db_table)
        self.refresh(FeedCollection._meta.db_table)
        self.refresh(FeedShelf._meta.db_table)

    def _search(self, q):
        res = self.client.get(self.url, data={'q': 'feed'})
        return res, json.loads(res.content)

    def test_query_slug(self):
        res, data = self._search('feed')
        eq_(res.status_code, 200)

        eq_(data['apps'][0]['id'], self.app.id)
        eq_(data['brands'][0]['id'], self.brand.id)
        eq_(data['collections'][0]['id'], self.collection.id)
        eq_(data['shelves'][0]['id'], self.shelf.id)


class TestFeedShelfPublishView(BaseTestFeedItemViewSet, amo.tests.TestCase):
    fixtures = BaseTestFeedItemViewSet.fixtures + FeedTestMixin.fixtures

    def setUp(self):
        super(TestFeedShelfPublishView, self).setUp()
        self.shelf = self.feed_shelf_factory()
        self.url = reverse('api-v2:feed-shelf-publish', args=[self.shelf.id])
        self.feed_permission()

    def test_publish(self):
        res = self.client.put(self.url)
        data = json.loads(res.content)
        eq_(res.status_code, 201)

        eq_(data['carrier'],
            mkt.carriers.CARRIER_CHOICE_DICT[self.shelf.carrier].slug)
        eq_(data['region'],
            mkt.regions.REGIONS_CHOICES_ID_DICT[self.shelf.region].slug)
        eq_(data['shelf']['id'], self.shelf.id)

    def test_publish_overwrite(self):
        self.client.put(self.url)
        eq_(FeedItem.objects.count(), 1)
        assert FeedItem.objects.filter(shelf_id=self.shelf.id).exists()

        new_shelf = self.feed_shelf_factory()
        new_url = reverse('api-v2:feed-shelf-publish', args=[new_shelf.id])
        self.client.put(new_url)
        eq_(FeedItem.objects.count(), 1)
        assert FeedItem.objects.filter(shelf_id=new_shelf.id).exists()

    def test_404(self):
        self.url = reverse('api-v2:feed-shelf-publish', args=[8008135])
        res = self.client.put(self.url)
        eq_(res.status_code, 404)


class TestFeedView(FeedTestMixin, RestOAuth):
    fixtures = fixture('webapp_337141') + RestOAuth.fixtures

    def setUp(self):
        super(TestFeedView, self).setUp()
        self.url = reverse('api-v2:feed.get')
        self.carrier = 'tmn'
        self.carrier_id = CARRIER_MAP[self.carrier].id
        self.region = 'us'
        self.region_id = REGIONS_DICT[self.region].id

    def create_feed(self, n):
        self.feed_items = []
        for i in xrange(n):
            app = app_factory()
            feedapp = self.feed_app_factory(app_id=app.id)
            feeditem = FeedItem.objects.create(carrier=self.carrier_id,
                app=feedapp, region=self.region_id, item_type='app')
            self.feed_items.append(feeditem)

    def create_shelf(self):
        feedshelf = self.feed_shelf_factory(carrier=self.carrier_id,
                                            region=self.region_id)
        self.shelf = FeedItem.objects.create(
            carrier=self.carrier_id, region=self.region_id, item_type='shelf',
            shelf=feedshelf)

    def get(self, client, **kwargs):
        res = client.get(self.url, kwargs)
        data = json.loads(res.content)
        return res, data

    def test_get_anon(self):
        res, data = self.get(self.anon, carrier=self.carrier,
                             region=self.region)
        eq_(res.status_code, 200)
        return res, data

    def test_get_authed(self):
        res, data = self.get(self.client, carrier=self.carrier,
                             region=self.region)
        eq_(res.status_code, 200)
        return res, data

    def test_get_shelf(self):
        self.create_shelf()
        res, data = self.test_get_anon()
        eq_(data['shelf']['id'], self.shelf.id)
        eq_(data['feed'], [])

    def test_get_feed(self):
        feed_size = 3
        self.create_feed(feed_size)
        res, data = self.test_get_anon()
        eq_(data['shelf'], None)
        eq_(len(data['feed']), feed_size)

    def test_get_both(self):
        feed_size = 3
        self.create_shelf()
        self.create_feed(feed_size)
        res, data = self.test_get_anon()
        eq_(data['shelf']['id'], self.shelf.id)
        eq_(len(data['feed']), feed_size)
        return res, data

    def test_shelf_mismatch(self):
        self.test_get_both()
        self.shelf.update(region=0)
        res, data = self.test_get_anon()
        eq_(data['shelf'], None)

    def test_feed_mismatch(self):
        self.test_get_both()
        for item in self.feed_items:
            item.update(region=0)
        res, data = self.test_get_anon()
        eq_(data['feed'], [])
