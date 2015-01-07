from nose.tools import eq_

import mkt.site.tests
from lib.es.models import Reindexing


class TestReindexing(mkt.site.tests.TestCase):

    def test_flag_reindexing(self):
        assert Reindexing.objects.count() == 0

        # Flagging for the first time.
        res = Reindexing.flag_reindexing('foo', 'bar', 'baz')
        eq_(Reindexing.objects.filter(alias='foo').count(), 1)
        eq_(res.alias, 'foo')
        eq_(res.old_index, 'bar')
        eq_(res.new_index, 'baz')

        # Flagging for the second time.
        res = Reindexing.flag_reindexing('foo', 'bar', 'baz')
        assert Reindexing.objects.filter(alias='foo').count() == 1
        assert res is None

    def test_unflag_reindexing(self):
        assert Reindexing.objects.filter(alias='foo').count() == 0

        # Unflagging unflagged database does nothing.
        Reindexing.unflag_reindexing(alias='foo')
        assert Reindexing.objects.filter(alias='foo').count() == 0

        # Flag, then unflag.
        Reindexing.objects.create(alias='foo', new_index='bar',
                                  old_index='baz')
        assert Reindexing.objects.filter(alias='foo').count() == 1

        Reindexing.unflag_reindexing(alias='foo')
        assert Reindexing.objects.filter(alias='foo').count() == 0

        # Unflagging another alias doesn't clash.
        Reindexing.objects.create(alias='bar', new_index='bar',
                                  old_index='baz')
        Reindexing.unflag_reindexing(alias='foo')
        assert Reindexing.objects.filter(alias='bar').count() == 1

    def test_is_reindexing(self):
        assert not Reindexing.is_reindexing()

        Reindexing.objects.create(alias='foo', new_index='bar',
                                  old_index='baz')
        assert Reindexing.is_reindexing()

    def test_get_indices(self):
        # Not reindexing.
        assert not Reindexing.objects.filter(alias='foo').exists()
        assert Reindexing.get_indices('foo') == ['foo']

        # Reindexing on 'foo'.
        Reindexing.objects.create(alias='foo', new_index='bar',
                                  old_index='baz')
        self.assertSetEqual(Reindexing.get_indices('foo'), ['bar', 'baz'])

        # Doesn't clash on other aliases.
        self.assertSetEqual(Reindexing.get_indices('other'), ['other'])
