from nose.tools import eq_

import amo
from mkt.search.indexers import BaseIndexer


class TestBaseIndexer(amo.tests.TestCase):

    def setUp(self):
        self.indexer = BaseIndexer

    def test_there_can_be_only_one(self):
        es1 = self.indexer().get_es()
        es2 = self.indexer().get_es()
        eq_(id(es1), id(es2))
