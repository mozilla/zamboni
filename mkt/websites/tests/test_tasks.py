import os

from django.conf import settings
from nose.tools import eq_, ok_

import mock

import mkt
import mkt.site.tests
from mkt.site.storage_utils import public_storage
from mkt.site.utils import ImageCheck, website_factory
from mkt.websites.models import Website
from mkt.websites.tasks import fetch_promo_imgs


class TestFetchPromoImgs(mkt.site.tests.TestCase):
    def setUp(self):
        self.website = website_factory()

    @mock.patch('mkt.developers.tasks.pngcrush_image')
    @mock.patch('mkt.developers.tasks.requests.get')
    def test_saves_promo_img(self, requests_mock, crush_mock):
        img_path = os.path.join(settings.ROOT, 'mkt', 'site', 'tests',
                                'images', 'game_1050.jpg')

        # Mock the image fetch request.
        with open(img_path, 'r') as content:
            requests_mock.return_value = mock.Mock(
                content=content.read(),
                headers={'ok': 'ok'},
                status_code=200)

        result = fetch_promo_imgs(self.website.pk, 'http://mocked_url.ly')
        ok_(result)

        website = Website.objects.all()[0]
        eq_(website.promo_img_hash, '215dd2a2')

        # Check the actual saved image on disk.
        img_dir = website.get_promo_img_dir()
        for size in mkt.PROMO_IMG_SIZES:
            img_path = os.path.join(img_dir, '%s-%s.png' % (str(website.id),
                                                            size))
            with public_storage.open(img_path, 'r') as img:
                checker = ImageCheck(img)
                assert checker.is_image()
                eq_(checker.img.size[0], size)
