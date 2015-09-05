from nose.tools import eq_

import mkt.site.tests

import mkt.carriers
import mkt.feed.constants as feed
import mkt.regions
from mkt.feed.models import (FeedApp, FeedBrand, FeedCollection, FeedItem,
                             FeedShelf)
from mkt.feed.tests.test_models import FeedTestMixin
from mkt.webapps.models import Preview, Webapp


class BaseFeedIndexerTest(object):

    def test_model(self):
        eq_(self.indexer.get_model(), self.model)

    def test_get_mapping_ok(self):
        assert isinstance(self.indexer.get_mapping(), dict)

    def _get_doc(self):
        return self.indexer.extract_document(self.obj.pk, self.obj)

    def _get_test_l10n(self):
        return {'en-US': 'ustext', 'de': 'detext'}

    def _assert_test_l10n(self, ts_obj):
        eq_(ts_obj, [{'lang': 'de', 'string': 'detext'},
                     {'lang': 'en-US', 'string': 'ustext'}])


class TestFeedAppIndexer(FeedTestMixin, BaseFeedIndexerTest,
                         mkt.site.tests.TestCase):

    def setUp(self):
        self.app = Webapp.objects.get(pk=337141)
        self.obj = self.feed_app_factory(
            background_color='#DDDDDD', image_hash='LOL',
            description=self._get_test_l10n(), pullquote_attribution='mscott',
            pullquote_rating=4, pullquote_text=self._get_test_l10n(),
            app_type=feed.FEEDAPP_QUOTE)
        self.obj.update(preview=Preview.objects.create(
            webapp=self.app, sizes={'thumbnail': [50, 50]}))

        self.indexer = self.obj.get_indexer()()
        self.model = FeedApp

    def test_extract(self):
        doc = self._get_doc()
        eq_(doc['id'], self.obj.id)
        eq_(doc['app'], self.app.id)
        eq_(doc['background_color'], '#DDDDDD')
        self._assert_test_l10n(doc['description_translations'])
        eq_(doc['image_hash'], 'LOL')
        eq_(doc['item_type'], feed.FEED_TYPE_APP)
        eq_(doc['preview'], {'id': self.obj.preview.id,
                             'thumbnail_size': [50, 50],
                             'thumbnail_url': self.obj.preview.thumbnail_url})
        eq_(doc['pullquote_attribution'], 'mscott')
        eq_(doc['pullquote_rating'], 4)
        self._assert_test_l10n(doc['pullquote_text_translations'])
        assert self.app.name.localized_string in doc['search_names']
        eq_(doc['slug'], self.obj.slug)
        eq_(doc['type'], self.obj.type)


class TestFeedBrandIndexer(FeedTestMixin, BaseFeedIndexerTest,
                           mkt.site.tests.TestCase):

    def setUp(self):
        self.obj = self.feed_brand_factory()
        self.indexer = self.obj.get_indexer()()
        self.model = FeedBrand

    def test_extract(self):
        doc = self._get_doc()
        eq_(doc['id'], self.obj.id)
        eq_(doc['apps'], list(self.obj.apps().values_list('id', flat=True)))
        eq_(doc['item_type'], feed.FEED_TYPE_BRAND)
        eq_(doc['layout'], self.obj.layout)
        eq_(doc['slug'], self.obj.slug)
        eq_(doc['type'], self.obj.type)


class TestFeedCollectionIndexer(FeedTestMixin, BaseFeedIndexerTest,
                                mkt.site.tests.TestCase):

    def setUp(self):
        self.app_ids = [mkt.site.tests.app_factory().id for app in range(3)]
        self.obj = self.feed_collection_factory(
            app_ids=self.app_ids, name=self._get_test_l10n(),
            description=self._get_test_l10n(), image_hash='LOL',
            coll_type=feed.COLLECTION_PROMO, grouped=True)
        self.indexer = self.obj.get_indexer()()
        self.model = FeedCollection

    def test_extract(self):
        doc = self._get_doc()
        eq_(doc['id'], self.obj.id)
        self.assertSetEqual(doc['apps'], self.app_ids)
        self._assert_test_l10n(doc['description_translations'])
        eq_(doc['group_apps'], {doc['apps'][0]: 0,
                                doc['apps'][1]: 0,
                                doc['apps'][2]: 1})
        eq_(doc['group_names'],
            [{'group_translations': [{'lang': 'en-US',
                                      'string': 'first-group'}]},
             {'group_translations': [{'lang': 'en-US',
                                      'string': 'second-group'}]}])
        eq_(doc['image_hash'], 'LOL')
        eq_(doc['item_type'], feed.FEED_TYPE_COLL)
        self._assert_test_l10n(doc['name_translations'])
        assert self.obj.name.localized_string in doc['search_names']
        eq_(doc['slug'], self.obj.slug)
        eq_(doc['type'], self.obj.type)


class TestFeedShelfIndexer(FeedTestMixin, BaseFeedIndexerTest,
                           mkt.site.tests.TestCase):

    def setUp(self):
        self.app_ids = [mkt.site.tests.app_factory().id for app in range(3)]
        self.obj = self.feed_shelf_factory(
            app_ids=self.app_ids, name=self._get_test_l10n(),
            description=self._get_test_l10n(), image_hash='LOL',
            image_landing_hash='ROFL', grouped=True)
        self.indexer = self.obj.get_indexer()()
        self.model = FeedShelf

    def test_extract(self):
        doc = self._get_doc()
        eq_(doc['id'], self.obj.id)
        self.assertSetEqual(doc['apps'], self.app_ids)
        eq_(doc['carrier'],
            mkt.carriers.CARRIER_CHOICE_DICT[self.obj.carrier].slug)
        self._assert_test_l10n(doc['description_translations'])
        eq_(doc['image_hash'], 'LOL')
        eq_(doc['image_landing_hash'], 'ROFL')
        self._assert_test_l10n(doc['name_translations'])
        eq_(doc['group_apps'], {doc['apps'][0]: 0,
                                doc['apps'][1]: 0,
                                doc['apps'][2]: 1})
        eq_(doc['group_names'],
            [{'group_translations': [{'lang': 'en-US',
                                      'string': 'first-group'}]},
             {'group_translations': [{'lang': 'en-US',
                                      'string': 'second-group'}]}])
        eq_(doc['region'],
            mkt.regions.REGIONS_CHOICES_ID_DICT[self.obj.region].slug)
        assert self.obj.name.localized_string in doc['search_names']
        eq_(doc['slug'], self.obj.slug)


class TestFeedItemIndexer(FeedTestMixin, BaseFeedIndexerTest,
                          mkt.site.tests.TestCase):

    def setUp(self):
        self.obj = self.feed_item_factory(item_type=feed.FEED_TYPE_APP,
                                          order=5)
        self.indexer = self.obj.get_indexer()()
        self.model = FeedItem

    def test_extract(self):
        doc = self._get_doc()
        eq_(doc['id'], self.obj.id)
        eq_(doc['carrier'], self.obj.carrier)
        eq_(doc['category'], None)
        eq_(doc['item_type'], feed.FEED_TYPE_APP)
        eq_(doc['order'], self.obj.order + 1)
        eq_(doc['region'], self.obj.region)
        eq_(doc['app'], self.obj.app_id)
        eq_(doc['brand'], None)
        eq_(doc['collection'], None)
        eq_(doc['shelf'], None)
