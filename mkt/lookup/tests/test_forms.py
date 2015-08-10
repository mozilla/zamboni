from django.core.files.uploadedfile import SimpleUploadedFile

from nose.tools import eq_, ok_

import mkt.site.tests
from mkt.lookup.forms import (TransactionSearchForm, TransactionRefundForm,
                              PromoImgForm)
from mkt.site.storage_utils import local_storage
from mkt.site.tests.test_utils_ import get_image_path


class TestTransactionSearchForm(mkt.site.tests.TestCase):
    def test_basic(self):
        """Test the form doesn't crap out."""
        self.check_valid({'q': 12345}, True)

    def test_str_number(self):
        self.check_valid({'q': '12345'})

    def check_valid(self, data, valid=True):
        form = TransactionSearchForm(data)
        eq_(form.is_valid(), valid)


class TestTransactionRefundForm(mkt.site.tests.TestCase):
    def test_not_fake(self):
        with self.settings(BANGO_FAKE_REFUNDS=False):
            assert 'fake' not in TransactionRefundForm().fields.keys()

    def test_fake(self):
        with self.settings(BANGO_FAKE_REFUNDS=True):
            assert 'fake' in TransactionRefundForm().fields.keys()


class TestPromoImgForm(mkt.site.tests.TestCase):
    def test_ok(self):
        app = mkt.site.tests.app_factory()

        with local_storage.open(get_image_path('game_1920.jpg')) as f:
            img_file = SimpleUploadedFile('game_1920.jpg', f.read(),
                                          content_type='image/jpg')
            form = PromoImgForm({}, {'promo_img': img_file})

            ok_(form.is_valid())
            form.save(app)

    def test_not_image_not_ok(self):
        form = PromoImgForm({}, {'promo_img': 'lol'})
        ok_(not form.is_valid())

    def test_too_small_not_ok(self):
        with local_storage.open(get_image_path('mkt_icon_72.png')) as f:
            img_file = SimpleUploadedFile('mkt_icon_72.png', f.read(),
                                          content_type='image/png')
            form = PromoImgForm({}, {'promo_img': img_file})
            ok_(not form.is_valid())

    def test_animated_not_ok(self):
        with local_storage.open(get_image_path('animated.gif')) as f:
            img_file = SimpleUploadedFile('animated.gif', f.read(),
                                          content_type='image/gif')
            form = PromoImgForm({}, {'promo_img': img_file})
            ok_(not form.is_valid())
