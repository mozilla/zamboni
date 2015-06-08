from django.core.urlresolvers import reverse

from nose.tools import eq_

from mkt.lookup.serializers import WebsiteLookupSerializer
from mkt.site.tests import ESTestCase
from mkt.websites.indexers import WebsiteIndexer
from mkt.websites.utils import website_factory


class TestWebsiteLookupSerializer(ESTestCase):

    def setUp(self):
        self.website = website_factory()
        self.refresh('website')

    def serialize(self):
        obj = WebsiteIndexer.search().filter(
            'term', id=self.website.pk).execute().hits[0]
        return WebsiteLookupSerializer(obj).data

    def test_basic(self):
        data = self.serialize()
        eq_(data['id'], self.website.id)
        eq_(data['name'], {'en-US': self.website.name})
        eq_(data['url'],
            reverse('lookup.website_summary', args=[self.website.id]))
