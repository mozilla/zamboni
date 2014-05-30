from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase

from lib.utils import validate_settings


class TestValidate(TestCase):

    def test_secret_key(self):
        with self.settings(DEBUG=True, SECRET_KEY='please change this'):
            validate_settings()

        with self.settings(DEBUG=False, SECRET_KEY='please change this'):
            with self.assertRaises(ImproperlyConfigured):
                validate_settings()

        with self.settings(DEBUG=False, SECRET_KEY='so changed'):
            validate_settings()
