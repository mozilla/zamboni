from nose.tools import eq_, ok_

from mkt.search.forms import TAG_CHOICES
from mkt.site.tests import TestCase


class TestTagChoices(TestCase):
    def setUp(self):
        self.tags_dict = dict(TAG_CHOICES)

    def _tag_exists(self, tag):
        ok_(tag in self.tags_dict.keys())
        eq_(tag, self.tags_dict[tag])

    def test_featured_website_tags(self):
        self._tag_exists('featured-website')
        self._tag_exists('featured-website-fr')
        self._tag_exists('featured-website-restofworld')
