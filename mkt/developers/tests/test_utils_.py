from django.core.files.storage import default_storage as storage

import mkt.site.tests
from mkt.developers.utils import check_upload
from mkt.site.tests.test_utils_ import get_image_path


class TestCheckUpload(mkt.site.tests.TestCase, mkt.site.tests.MktPaths):
    # TODO: increase coverage on check_upload.

    def test_not_valid(self):
        with self.assertRaises(ValueError):
            check_upload([], 'graphic', 'image/jpg')

    def test_valid(self):
        with storage.open(get_image_path('preview.jpg')) as f:
            errors, hash = check_upload(f, 'preview', 'image/png')
            assert not errors
