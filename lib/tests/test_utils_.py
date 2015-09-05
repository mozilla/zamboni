from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase

from nose.tools import eq_

from lib.utils import static_url, update_csp, validate_settings


class TestValidate(TestCase):

    def test_secret_key(self):
        with self.settings(DEBUG=True,
                           IN_TEST_SUITE=False,
                           SECRET_KEY='please change this',
                           SITE_URL='http://testserver'):
            validate_settings()

        with self.settings(DEBUG=False,
                           IN_TEST_SUITE=False,
                           SECRET_KEY='please change this',
                           SITE_URL='http://testserver'):
            update_csp()
            with self.assertRaises(ImproperlyConfigured):
                validate_settings()

        with self.settings(DEBUG=False,
                           IN_TEST_SUITE=False,
                           SECRET_KEY='so changed',
                           SESSION_COOKIE_SECURE=True,
                           APP_PURCHASE_SECRET='so changed'):
            update_csp()
            validate_settings()

    def test_http(self):
        with self.settings(CSP_SCRIPT_SRC=('http://f.c'), DEBUG=True,
                           IN_TEST_SUITE=False):
            validate_settings()

    def test_http_not_debug(self):
        with self.settings(CSP_SCRIPT_SRC=('http://f.c'), DEBUG=False,
                           IN_TEST_SUITE=False):
            with self.assertRaises(ImproperlyConfigured):
                validate_settings()

    def test_update_csp(self):
        with self.settings(CSP_SCRIPT_SRC=('https://f.c', 'self',
                                           'http://f.c'),
                           DEBUG=False,
                           IN_TEST_SUITE=False):
            update_csp()
            self.assertSetEqual(set(settings.CSP_SCRIPT_SRC),
                                set(('https://f.c', 'self')))

        with self.settings(CSP_SCRIPT_SRC=('https://f.c', 'self',
                                           'http://f.c'),
                           DEBUG=True):
            update_csp()
            self.assertSetEqual(set(settings.CSP_SCRIPT_SRC),
                                set(('https://f.c', 'self', 'http://f.c')))


class TestURL(TestCase):

    def test_url(self):
        with self.settings(WEBAPPS_RECEIPT_URL='/v', SITE_URL='http://f.com'):
            eq_(static_url('WEBAPPS_RECEIPT_URL'), 'http://f.com/v')

        with self.settings(DEBUG=True, SERVE_TMP_PATH=True):
            eq_(static_url('WEBAPPS_RECEIPT_URL'),
                'http://testserver/receipt-verifier/')

        with self.settings(WEBAPPS_RECEIPT_URL='http://f.com'):
            eq_(static_url('WEBAPPS_RECEIPT_URL'), 'http://f.com')

    def test_leading_slash(self):
        with self.settings(WEBAPP_ICON_URL='v', DEBUG=True,
                           SERVE_TMP_PATH=True):
            eq_(static_url('WEBAPP_ICON_URL'), 'http://testserver/tmp/v')

        with self.settings(WEBAPP_ICON_URL='/v', DEBUG=True,
                           SERVE_TMP_PATH=True):
            eq_(static_url('WEBAPP_ICON_URL'), 'http://testserver/tmp/v')
