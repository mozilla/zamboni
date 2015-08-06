import mock
from nose.tools import eq_

from mkt.constants.applications import (DEVICE_DESKTOP, DEVICE_GAIA,
                                        DEVICE_TYPE_LIST)
from mkt.constants.regions import URY, USA
from mkt.site.tests import TestCase
from mkt.websites.models import Website
from mkt.websites.utils import website_factory


class TestWebsiteModel(TestCase):
    def test_devices(self):
        website = Website(devices=[device.id for device in DEVICE_TYPE_LIST])
        eq_(sorted(website.devices),
            sorted([device.id for device in DEVICE_TYPE_LIST]))

    def test_devices_names(self):
        website = Website(devices=[DEVICE_DESKTOP.id, DEVICE_GAIA.id])
        eq_(sorted(website.device_names), ['desktop', 'firefoxos'])

    def test_get_icon_url(self):
        website = Website(pk=1, icon_type='image/png')
        expected = ('/0/%d-32.png?modified=never' % (website.pk,))
        assert website.get_icon_url(32).endswith(expected), (
            'Expected %s, got %s' % (expected, website.get_icon_url(32)))

    def test_get_icon_url_big_pk(self):
        website = Website(pk=9876, icon_type='image/png')
        expected = ('/%s/%d-32.png?modified=never' % (str(website.pk)[:-3],
                                                      website.pk))
        assert website.get_icon_url(32).endswith(expected), (
            'Expected %s, got %s' % (expected, website.get_icon_url(32)))

    def test_get_icon_url_bigger_pk(self):
        website = Website(pk=98765432, icon_type='image/png')
        expected = ('/%s/%d-32.png?modified=never' % (str(website.pk)[:-3],
                                                      website.pk))
        assert website.get_icon_url(32).endswith(expected), (
            'Expected %s, got %s' % (expected, website.get_icon_url(32)))

    def test_get_icon_url_hash(self):
        website = Website(pk=1, icon_type='image/png', icon_hash='abcdef')
        assert website.get_icon_url(32).endswith('?modified=abcdef')

    def test_get_icon_no_icon_blue(self):
        website = Website(pk=8)
        url = website.get_icon_url(32)
        assert url.endswith('hub/asia-australia-blue-32.png'), url

    def test_get_icon_no_icon_pink(self):
        website = Website(pk=164)
        url = website.get_icon_url(32)
        assert url.endswith('hub/europe-africa-pink-32.png'), url

    def test_get_preferred_regions(self):
        website = Website()
        website.preferred_regions = [URY.id, USA.id]
        eq_([r.slug for r in website.get_preferred_regions()],
            [USA.slug, URY.slug])


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
