from nose.tools import eq_

from mkt.site.tests import TestCase
from mkt.websites.models import Website
from mkt.websites.utils import website_factory


class TestWebsiteIndexer(TestCase):

    def setUp(self):
        self.indexer = Website.get_indexer()()

    def test_model(self):
        eq_(self.indexer.get_model(), Website)

    def test_get_mapping_ok(self):
        assert isinstance(self.indexer.get_mapping(), dict)

    def _get_doc(self):
        return self.indexer.extract_document(self.obj.pk, self.obj)

    def test_extract(self):
        self.obj = website_factory()
        doc = self._get_doc()
        eq_(doc['id'], self.obj.id)
