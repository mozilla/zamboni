from nose.tools import eq_, ok_

from django.core.exceptions import ValidationError

import amo.tests
from mkt.feed.models import FeedApp, FeedBrand
from mkt.webapps.models import Webapp

from .test_views import FeedAppMixin


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
