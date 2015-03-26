import mock
from nose.tools import eq_

from mkt.site.tests import TestCase
from mkt.websites.models import Website
from mkt.websites.utils import website_factory


class TestWebsiteESIndexation(TestCase):
    @mock.patch('mkt.search.indexers.BaseIndexer.index_ids')
    def test_update_search_index(self, update_mock):
        website = website_factory()
        update_mock.assert_called_once_with([website.pk])

    @mock.patch('mkt.search.indexers.BaseIndexer.unindex')
    def test_delete_search_index(self, delete_mock):
        for x in xrange(4):
            website_factory()
        count = Website.objects.count()
        Website.objects.all().delete()
        eq_(delete_mock.call_count, count)
