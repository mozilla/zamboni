from nose.tools import eq_

import amo.tests

import mkt.carriers
import mkt.regions
from mkt.feed.models import FeedApp, FeedBrand, FeedCollection, FeedShelf
from mkt.feed.tests.test_models import FeedTestMixin
from mkt.webapps.models import Webapp


class BaseFeedIndexerTest(object):

    def test_model(self):
        eq_(self.indexer.get_model(), self.model)

    def _get_doc(self):
        return self.indexer.extract_document(self.obj.pk, self.obj)


class TestFeedAppIndexer(FeedTestMixin, BaseFeedIndexerTest,
                         amo.tests.TestCase):

    def setUp(self):
        self.app = Webapp.objects.get(pk=337141)
        self.obj = self.feed_app_factory()
        self.indexer = self.obj.get_indexer()()
        self.model = FeedApp

    def test_extract(self):
        doc = self._get_doc()
        eq_(doc['id'], self.obj.id)
        assert self.app.name.localized_string in doc['name']
        eq_(doc['slug'], self.obj.slug)
        eq_(doc['type'], self.obj.type)


class TestFeedBrandIndexer(FeedTestMixin, BaseFeedIndexerTest,
                           amo.tests.TestCase):

    def setUp(self):
        self.obj = self.feed_brand_factory()
        self.indexer = self.obj.get_indexer()()
        self.model = FeedBrand

    def test_extract(self):
        doc = self._get_doc()
        eq_(doc['id'], self.obj.id)
        eq_(doc['slug'], self.obj.slug)
        eq_(doc['type'], self.obj.type)


class TestFeedCollectionIndexer(FeedTestMixin, BaseFeedIndexerTest,
                                amo.tests.TestCase):

    def setUp(self):
        self.obj = self.feed_collection_factory()
        self.indexer = self.obj.get_indexer()()
        self.model = FeedCollection

    def test_extract(self):
        doc = self._get_doc()
        eq_(doc['id'], self.obj.id)
        assert self.obj.name.localized_string in doc['name']
        eq_(doc['slug'], self.obj.slug)
        eq_(doc['type'], self.obj.type)


class TestFeedShelfIndexer(FeedTestMixin, BaseFeedIndexerTest,
                           amo.tests.TestCase):

    def setUp(self):
        self.obj = self.feed_shelf_factory()
        self.indexer = self.obj.get_indexer()()
        self.model = FeedShelf

    def test_extract(self):
        doc = self._get_doc()
        eq_(doc['id'], self.obj.id)
        assert self.obj.name.localized_string in doc['name']
        eq_(doc['slug'], self.obj.slug)
        eq_(doc['carrier'],
            mkt.carriers.CARRIER_CHOICE_DICT[self.obj.carrier].slug)
        eq_(doc['region'],
            mkt.regions.REGIONS_CHOICES_ID_DICT[self.obj.region].slug)
