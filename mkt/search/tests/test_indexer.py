from nose.tools import eq_

from mkt.search.indexers import BaseIndexer
from mkt.site.tests import TestCase


class TestBaseIndexer(TestCase):

    def setUp(self):
        self.indexer = BaseIndexer

    def test_there_can_be_only_one(self):
        es1 = self.indexer().get_es()
        es2 = self.indexer().get_es()
        eq_(id(es1), id(es2))
