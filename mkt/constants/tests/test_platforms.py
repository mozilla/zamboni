from django.test.client import RequestFactory
from nose.tools import eq_
from tower import ugettext as _

import mkt.site.tests
from mkt.constants.platforms import FREE_PLATFORMS, PAID_PLATFORMS


class TestPlatforms(mkt.site.tests.TestCase):

    def test_free_platforms(self):
        platforms = FREE_PLATFORMS()
        expected = (
            ('free-firefoxos', _('Firefox OS')),
            ('free-desktop', _('Firefox for Desktop')),
            ('free-android-mobile', _('Firefox Mobile')),
            ('free-android-tablet', _('Firefox Tablet')),
        )
        eq_(platforms, expected)

    def test_paid_platforms_default(self):
        platforms = PAID_PLATFORMS()
        expected = (
            ('paid-firefoxos', _('Firefox OS')),
        )
        eq_(platforms, expected)

    def test_paid_platforms_android_payments_waffle_on(self):
        self.create_flag('android-payments')
        platforms = PAID_PLATFORMS(request=RequestFactory())
        expected = (
            ('paid-firefoxos', _('Firefox OS')),
            ('paid-android-mobile', _('Firefox Mobile')),
            ('paid-android-tablet', _('Firefox Tablet')),
        )
        eq_(platforms, expected)
