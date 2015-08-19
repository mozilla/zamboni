import os

from django.conf import settings

from nose.tools import ok_

import mkt.site.tests
from mkt.developers.utils import check_upload
from mkt.site.storage_utils import local_storage, private_storage
from mkt.site.tests.test_utils_ import get_image_path


class TestCheckUpload(mkt.site.tests.TestCase, mkt.site.tests.MktPaths):
    def test_upload_type_not_recognized(self):
        with self.assertRaises(ValueError):
            check_upload([], 'graphic', 'image/jpg')

    def test_icon_ok(self):
        with local_storage.open(get_image_path('mozilla-sq.png')) as f:
            errors, upload_hash = check_upload(f, 'icon', 'image/png')
            ok_(not errors)
            ok_(upload_hash)

            tmp_img_path = os.path.join(settings.TMP_PATH, 'icon',
                                        upload_hash)
            ok_(private_storage.exists(tmp_img_path))

    def test_icon_too_small(self):
        with local_storage.open(get_image_path('mkt_icon_72.png')) as f:
            errors, upload_hash = check_upload(f, 'icon', 'image/png')
            ok_(errors)
            ok_(upload_hash)

            tmp_img_path = os.path.join(settings.TMP_PATH, 'icon',
                                        upload_hash)
            ok_(private_storage.exists(tmp_img_path))

    def test_preview_ok(self):
        with local_storage.open(get_image_path('preview.jpg')) as f:
            errors, upload_hash = check_upload(f, 'preview', 'image/png')
            ok_(not errors)
            ok_(upload_hash)

            tmp_img_path = os.path.join(settings.TMP_PATH, 'preview',
                                        upload_hash)
            ok_(private_storage.exists(tmp_img_path))

    def test_preview_too_small(self):
        with local_storage.open(get_image_path('mkt_icon_72.png')) as f:
            errors, upload_hash = check_upload(f, 'preview', 'image/png')
            ok_(errors)
            ok_(upload_hash)

            tmp_img_path = os.path.join(settings.TMP_PATH, 'preview',
                                        upload_hash)
            ok_(private_storage.exists(tmp_img_path))

    def test_promo_img_ok(self):
        with local_storage.open(get_image_path('game_1050.jpg')) as f:
            errors, upload_hash = check_upload(f, 'promo_img', 'image/png')
            ok_(not errors)
            ok_(upload_hash)

            tmp_img_path = os.path.join(settings.TMP_PATH, 'promo_img',
                                        upload_hash)
            ok_(private_storage.exists(tmp_img_path))

    def test_promo_img_too_small(self):
        with local_storage.open(get_image_path('preview.jpg')) as f:
            errors, upload_hash = check_upload(f, 'promo_img', 'image/png')
            ok_(errors)
            ok_(upload_hash)

            tmp_img_path = os.path.join(settings.TMP_PATH, 'promo_img',
                                        upload_hash)
            ok_(private_storage.exists(tmp_img_path))
