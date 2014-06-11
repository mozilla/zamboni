from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase

from nose.tools import eq_

from lib.utils import static_url, validate_settings


class TestValidate(TestCase):

    def test_secret_key(self):
        with self.settings(DEBUG=True, IN_TEST_SUITE=False,
                           SECRET_KEY='please change this'):
            validate_settings()

        with self.settings(DEBUG=False, IN_TEST_SUITE=False,
                           SECRET_KEY='please change this'):
            with self.assertRaises(ImproperlyConfigured):
                validate_settings()

        with self.settings(DEBUG=False, IN_TEST_SUITE=False,
                           SECRET_KEY='so changed',
                           SESSION_COOKIE_SECURE=True,
                           APP_PURCHASE_SECRET='so changed'):
            validate_settings()


class TestURL(TestCase):

    def test_url(self):
        with self.settings(WEBAPPS_RECEIPT_URL='/v', SITE_URL='http://f.com'):
            eq_(static_url('WEBAPPS_RECEIPT_URL'), 'http://f.com/v')

        with self.settings(DEBUG=True, SERVE_TMP_PATH=True):
            eq_(static_url('WEBAPPS_RECEIPT_URL'),
                'http://testserver/tmp/verify/')

        with self.settings(WEBAPPS_RECEIPT_URL='http://f.com'):
            eq_(static_url('WEBAPPS_RECEIPT_URL'), 'http://f.com')

    def test_leading_slash(self):
        with self.settings(ADDON_ICON_URL='v', DEBUG=True,
                           SERVE_TMP_PATH=True):
            eq_(static_url('ADDON_ICON_URL'), 'http://testserver/tmp/v')

        with self.settings(ADDON_ICON_URL='/v', DEBUG=True,
                           SERVE_TMP_PATH=True):
            eq_(static_url('ADDON_ICON_URL'), 'http://testserver/tmp/v')
