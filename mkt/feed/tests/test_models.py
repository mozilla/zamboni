# -*- coding: utf-8 -*-
import random
import string

from django.core.exceptions import ValidationError

from nose.tools import eq_, ok_

import amo.tests

import mkt.feed.constants as feed
from mkt.feed.models import (FeedApp, FeedBrand, FeedCollection, FeedItem,
                             FeedShelf)
from mkt.site.fixtures import fixture
from mkt.webapps.models import Webapp


class FeedTestMixin(object):
    fixtures = fixture('webapp_337141')

    def feed_app_factory(self, app_id=None, app_type=feed.FEEDAPP_ICON,
                         **kwargs):
        count = FeedApp.objects.count()
        return FeedApp.objects.create(
            app_id=app_id or Webapp.objects.get(id=337141).id,
            slug='feed-app-%s' % count, type=app_type, **kwargs)

    def feed_brand_factory(self, app_ids=None, layout=feed.BRAND_GRID,
                           brand_type='mystery-app', **kwargs):
        count = FeedBrand.objects.count()
        brand = FeedBrand.objects.create(slug='feed-brand-%s' % count,
                                         type=brand_type, **kwargs)
        brand.set_apps(app_ids or [337141])
        return brand

    def feed_collection_factory(self, app_ids=None, name='test-coll',
                                coll_type=feed.COLLECTION_LISTING,
                                grouped=False, **kwargs):
        count = FeedCollection.objects.count()
        coll = FeedCollection.objects.create(
            name=name, slug='feed-coll-%s' % count, type=coll_type, **kwargs)
        app_ids = app_ids or [337141]
        coll.set_apps(app_ids)

        if grouped:
            for i, mem in enumerate(coll.feedcollectionmembership_set.all()):
                if i == len(app_ids) - 1 and len(app_ids) > 1:
                    mem.group = 'second-group'
                else:
                    mem.group = 'first-group'
                mem.save()

        return coll

    def feed_shelf_factory(self, app_ids=None, name='test-shelf',
                           carrier=1, region=1, **kwargs):
        count = FeedShelf.objects.count()
        shelf = FeedShelf.objects.create(
            background_color='#FF4E00', name=name,
            slug='feed-shelf-%s' % count, carrier=carrier, region=region,
            **kwargs)
        shelf.set_apps(app_ids or [337141])
        return shelf

    def feed_item_factory(self, carrier=1, region=1,
                          item_type=feed.FEED_TYPE_APP):
        """Creates a single FeedItem of any feed element type specified."""
        feed_item = FeedItem(carrier=carrier, region=region,
                             item_type=item_type)

        if item_type == feed.FEED_TYPE_APP:
            feed_item.app = self.feed_app_factory()
        elif item_type == feed.FEED_TYPE_BRAND:
            feed_item.brand = self.feed_brand_factory()
        elif item_type == feed.FEED_TYPE_COLL:
            feed_item.collection = self.feed_collection_factory()
        elif item_type == feed.FEED_TYPE_SHELF:
            feed_item.shelf = self.feed_shelf_factory()

        feed_item.save()
        return feed_item

    def feed_factory(self, carrier=1, region=1, item_types=None):
        """
        Takes a list of feed element types and creates FeedItems with those
        types. Returns a list of FeedItems.
        """
        item_types = item_types or [feed.FEED_TYPE_APP, feed.FEED_TYPE_BRAND,
                                    feed.FEED_TYPE_COLL, feed.FEED_TYPE_SHELF]

        feed_items = []
        for item_type in item_types:
            feed_items.append(
                self.feed_item_factory(carrier=carrier, region=region,
                                       item_type=item_type))
        return feed_items


class FeedAppMixin(object):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        self.feedapp_data = {
            'app': 337141,
            'background_color': '#B90000',
            'type': 'icon',
            'description': {
                'en-US': u'pan-fried potatoes'
            },
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
                       for _ in range(10)).lower()

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


class TestFeedApp(FeedAppMixin, amo.tests.TestCase):

    def setUp(self):
        super(TestFeedApp, self).setUp()
        self.feedapp_data.update(**self.pullquote_data)
        self.feedapp_data['app'] = (
            Webapp.objects.get(pk=self.feedapp_data['app']))

    def test_create(self):
        feedapp = FeedApp(**self.feedapp_data)
        ok_(isinstance(feedapp, FeedApp))
        feedapp.clean_fields()  # Tests validators on fields.
        feedapp.clean()  # Test model validation.
        feedapp.save()  # Tests required fields.

    def test_missing_pullquote_rating(self):
        del self.feedapp_data['pullquote_rating']
        self.test_create()

    def test_missing_pullquote_text(self):
        del self.feedapp_data['pullquote_text']
        with self.assertRaises(ValidationError):
            self.test_create()

    def test_pullquote_rating_fractional(self):
        """
        This passes because PositiveSmallIntegerField will coerce the float
        into an int, which effectively returns math.floor(value).
        """
        self.feedapp_data['pullquote_rating'] = 4.5
        self.test_create()

    def test_bad_pullquote_rating_low(self):
        self.feedapp_data['pullquote_rating'] = -1
        with self.assertRaises(ValidationError):
            self.test_create()

    def test_bad_pullquote_rating_high(self):
        self.feedapp_data['pullquote_rating'] = 6
        with self.assertRaises(ValidationError):
            self.test_create()


class TestFeedBrand(amo.tests.TestCase):

    def setUp(self):
        super(TestFeedBrand, self).setUp()
        self.apps = [amo.tests.app_factory() for i in xrange(3)]
        self.brand = None
        self.brand_data = {
            'slug': 'potato',
            'type': 1,
            'layout': 1
        }

    def test_create(self):
        self.brand = FeedBrand.objects.create(**self.brand_data)
        ok_(isinstance(self.brand, FeedBrand))
        for name, value in self.brand_data.iteritems():
            eq_(getattr(self.brand, name), value, name)

    def test_add_app(self):
        self.test_create()
        m = self.brand.add_app(self.apps[0], order=3)
        ok_(self.brand.apps(), [self.apps[0]])
        eq_(m.order, 3)
        eq_(m.app, self.apps[0])
        eq_(m.obj, self.brand)

    def test_add_app_sort_order_respected(self):
        self.test_add_app()
        self.brand.add_app(self.apps[1], order=1)
        ok_(self.brand.apps(), [self.apps[1], self.apps[0]])

    def test_add_app_no_order_passed(self):
        self.test_add_app()
        m = self.brand.add_app(self.apps[1])
        ok_(m.order, 4)

    def test_remove_app(self):
        self.test_add_app()
        ok_(self.apps[0] in self.brand.apps())
        removed = self.brand.remove_app(self.apps[0])
        ok_(removed)
        ok_(self.apps[0] not in self.brand.apps())

    def test_remove_app_not_in_brand(self):
        self.test_remove_app()
        removed = self.brand.remove_app(self.apps[1])
        ok_(not removed)

    def test_set_apps(self):
        self.test_add_app_sort_order_respected()
        new_apps = [app.pk for app in self.apps][::-1]
        self.brand.set_apps(new_apps)
        eq_(new_apps, [app.pk for app in self.brand.apps().no_cache()])

    def test_set_apps_nonexistant(self):
        self.test_add_app_sort_order_respected()
        with self.assertRaises(Webapp.DoesNotExist):
            self.brand.set_apps([99999])
