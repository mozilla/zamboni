from django.core.management import call_command

from mpconstants import collection_colors as colors
from nose.tools import eq_

from mkt.feed.models import FeedApp, FeedCollection
from mkt.site.tests import app_factory, TestCase


class TestMigrateCollectionColor(TestCase):

    def setUp(self):
        self.color_hex = colors.COLLECTION_COLORS_REVERSE.keys()[0]
        self.color_name = colors.COLLECTION_COLORS_REVERSE[self.color_hex]

    def test_app(self):
        obj = FeedApp.objects.create(app=app_factory(),
                                     background_color=self.color_hex)
        eq_(obj.color, None)
        call_command('migrate_collection_colors')
        eq_(FeedApp.objects.get(id=obj.id).color, self.color_name)

    def test_collection(self):
        obj = FeedCollection.objects.create(background_color=self.color_hex)
        eq_(obj.color, None)
        call_command('migrate_collection_colors')
        eq_(FeedCollection.objects.get(id=obj.id).color, self.color_name)

    def test_no_background_color(self):
        obj = FeedCollection.objects.create()
        eq_(obj.background_color, None)
        eq_(obj.color, None)
        call_command('migrate_collection_colors')
        eq_(obj.background_color, None)
        eq_(obj.color, None)

    def test_invalid_background_color(self):
        obj = FeedCollection.objects.create(background_color='#000000')
        eq_(obj.color, None)
        call_command('migrate_collection_colors')
        eq_(obj.color, None)
