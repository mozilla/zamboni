from nose.tools import eq_

import amo.tests
from mkt.tags.models import Tag


class TestTagManager(amo.tests.TestCase):

    def test_not_blocked(self):
        """Make sure Tag Manager filters right for not blocked tags."""
        tag1 = Tag(tag_text='abc', blocked=False)
        tag1.save()
        tag2 = Tag(tag_text='swearword', blocked=True)
        tag2.save()

        eq_(Tag.objects.all().count(), 2)
        eq_(Tag.objects.not_blocked().count(), 1)
        eq_(Tag.objects.not_blocked()[0], tag1)
