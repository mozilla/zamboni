import mock
from nose.tools import eq_, ok_

from django.core.files.storage import default_storage as storage

from lib.utils import static_url
from mkt.constants.applications import (DEVICE_DESKTOP, DEVICE_GAIA,
                                        DEVICE_TYPE_LIST)
from mkt.constants.regions import URY, USA
from mkt.site.storage_utils import storage_is_remote
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
        if not storage_is_remote():
            expected = (static_url('WEBSITE_ICON_URL')
                        % ('0', website.pk, 32, 'never'))
        else:
            path = '%s/%s-%s.png' % (website.get_icon_dir(), website.pk, 32)
            expected = '%s?modified=never' % storage.url(path)
        assert website.get_icon_url(32).endswith(expected), (
            'Expected %s, got %s' % (expected, website.get_icon_url(32)))

    def test_get_icon_url_big_pk(self):
        website = Website(pk=9876, icon_type='image/png')
        if not storage_is_remote():
            expected = (static_url('WEBSITE_ICON_URL')
                        % (str(website.pk)[:-3], website.pk, 32, 'never'))
        else:
            path = '%s/%s-%s.png' % (website.get_icon_dir(), website.pk, 32)
            expected = '%s?modified=never' % storage.url(path)
        assert website.get_icon_url(32).endswith(expected), (
            'Expected %s, got %s' % (expected, website.get_icon_url(32)))

    def test_get_icon_url_bigger_pk(self):
        website = Website(pk=98765432, icon_type='image/png')
        if not storage_is_remote():
            expected = (static_url('WEBSITE_ICON_URL')
                        % (str(website.pk)[:-3], website.pk, 32, 'never'))
        else:
            path = '%s/%s-%s.png' % (website.get_icon_dir(), website.pk, 32)
            expected = '%s?modified=never' % storage.url(path)
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

    def test_get_promo_img_url(self):
        website = Website(pk=337141)
        eq_(website.get_promo_img_url('640'), '')
        eq_(website.get_promo_img_url('1050'), '')

        website.promo_img_hash = 'chicken'
        ok_('website_promo_imgs/337/337141-640.png?modified=chicken' in
            website.get_promo_img_url('640'))
        ok_('website_promo_imgs/337/337141-1050.png?modified=chicken' in
            website.get_promo_img_url('1050'))


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
