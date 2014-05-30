from nose.tools import eq_

import amo
import amo.tests
from addons.helpers import flag, statusflags
from addons.models import Addon


class TestHelpers(amo.tests.TestCase):
    fixtures = ['base/addon_3615', 'base/users',
                'addons/featured', 'base/collections',
                'base/featured']

    def test_statusflags(self):
        ctx = {'APP': amo.FIREFOX, 'LANG': 'en-US'}

        # unreviewed
        a = Addon(status=amo.STATUS_UNREVIEWED)
        eq_(statusflags(ctx, a), 'unreviewed')

        # recommended
        featured = Addon.objects.get(pk=1003)
        eq_(statusflags(ctx, featured), 'featuredaddon')

        # category featured
        featured = Addon.objects.get(pk=1001)
        eq_(statusflags(ctx, featured), 'featuredaddon')

    def test_flags(self):
        ctx = {'APP': amo.FIREFOX, 'LANG': 'en-US'}

        # unreviewed
        a = Addon(status=amo.STATUS_UNREVIEWED)
        eq_(flag(ctx, a), '<h5 class="flag">Not Reviewed</h5>')

        # recommended
        featured = Addon.objects.get(pk=1003)
        eq_(flag(ctx, featured), '<h5 class="flag">Featured</h5>')

        # category featured
        featured = Addon.objects.get(pk=1001)
        eq_(flag(ctx, featured), '<h5 class="flag">Featured</h5>')
