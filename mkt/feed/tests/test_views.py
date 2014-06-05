# -*- coding: utf-8 -*-
import json
import random
import string

from django.core.urlresolvers import reverse

from nose.tools import eq_, ok_

import mkt.carriers
import mkt.regions
from addons.models import Preview
from amo.tests import app_factory
from mkt.api.tests.test_oauth import RestOAuth
from mkt.feed.models import FeedApp, FeedBrand, FeedCollection, FeedItem
from mkt.site.fixtures import fixture
from mkt.webapps.models import Webapp


class FeedAppMixin(object):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        self.feedapp_data = {
            'app': 337141,
            'background_color': '#B90000',
            'feedapp_type': 'icon',
            'description': {
                'en-US': u'pan-fried potatoes'
            },
            'has_image': False,
            'slug': self.random_slug()
        }
        self.pullquote_data = {
            'pullquote_text': {'en-US': u'The bést!'},
            'pullquote_rating': 4,
            'pullquote_attribution': u'Jamés Bod'
        }
        self.feedapps = []
        super(FeedAppMixin, self).setUp()

    def random_slug(self):
        return ''.join(random.choice(string.ascii_uppercase + string.digits)
                       for _ in range(10))

    def create_feedapps(self, n=2, **kwargs):
        data = dict(self.feedapp_data)
        data.update(kwargs)
        if not isinstance(data['app'], Webapp):
            data['app'] = Webapp.objects.get(pk=data['app'])

        feedapps = []
        for idx in xrange(n):
            data['slug'] = self.random_slug()
            feedapps.append(FeedApp.objects.create(**data))
        self.feedapps.extend(feedapps)

        return feedapps


class BaseTestFeedItemViewSet(RestOAuth):
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
        eq_(data['feedapp_type'], self.feedapp_data['feedapp_type'])

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

    def test_detail_anonymous(self):
        self._test_detail(self.anon)

    def test_detail_no_permission(self):
        self._test_detail(self.client)

    def test_detail_with_permission(self):
        self.feed_permission()
        self._test_detail(self.client)

    def test_with_image(self):
        self.feedapp = self.create_feedapps(1, has_image=True)[0]
        self.url = reverse('api-v2:feedapps-detail',
                           kwargs={'pk': self.feedapp.pk})
        self._test_detail(self.client)


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

    def make_item(self, **addtl):
        obj_data = self.data(slug='sprout')
        obj_data.update(addtl)
        self.item = self.model.objects.create(**obj_data)
        self.detail_url = reverse('api-v2:%s-detail' % self.url_basename,
                                  kwargs={'pk': self.item.pk})
        self.set_apps_url = self.detail_url + 'set_apps/'

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

    def set_apps(self, client, **kwargs):
        self.make_item()
        res = client.post(self.set_apps_url, json.dumps(kwargs))
        data = json.loads(res.content)
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

    def test_set_apps_anonymous(self):
        res, data = self.set_apps(self.anon)
        eq_(res.status_code, 403)

    def test_set_apps_no_permission(self):
        res, data = self.set_apps(self.client)
        eq_(res.status_code, 403)

    def test_set_apps_with_permission_three_apps(self):
        self.feed_permission()
        self.apps = [app_factory() for i in xrange(3)]
        new_apps = [app.pk for app in self.apps]
        res, data = self.set_apps(self.client, apps=new_apps)
        eq_(res.status_code, 200)
        eq_(new_apps, [app['id'] for app in data['apps']])

    def test_set_apps_with_permission_one_app(self):
        self.test_set_apps_with_permission_three_apps()
        if not self.apps:
            self.apps = [app_factory() for i in xrange(2)]
        new_apps = [self.apps[1].pk]
        res, data = self.set_apps(self.client, apps=new_apps)
        eq_(res.status_code, 200)
        eq_(new_apps, [app['id'] for app in data['apps']])

    def test_set_apps_invalid_app(self):
        self.feed_permission()
        res, data = self.set_apps(self.client)
        eq_(res.status_code, 400)


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
        'color': '#00AACC',
        'description': {'en-US': 'Potato french fries'},
        'name': {'en-US': 'Deep Fried'}
    }
    model = FeedCollection
    url_basename = 'feedcollections'

    def make_item(self):
        """
        Add additional unique fields: `description` and `name`.
        """
        super(TestFeedCollectionViewSet, self).make_item(
            description={'en-US': 'Baby Potato'}, name={'en-US': 'Sprout'})

    def test_create_missing_color(self):
        self.feed_permission()
        obj_data = self.data()
        del obj_data['color']
        res, data = self.create(self.client, **obj_data)
        eq_(res.status_code, 400)
        ok_('color' in data)

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
