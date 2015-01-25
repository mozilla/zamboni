# -*- coding: utf-8 -*-
from django.forms import ValidationError

from mock import patch
from nose.tools import eq_

from mkt.langpacks.utils import LanguagePackParser
from mkt.site.tests import TestCase


class TestLangPackUpload(TestCase):
    @patch('mkt.files.utils.WebAppParser.get_json_data')
    def test_upload_multiple_languages(self, get_json_data_mock):
        get_json_data_mock.return_value = {
            'role': 'langpack',
            'languages-provided': {
                'es': {},
                'de': {},
            },
            'languages-target': {
                'app://*.gaiamobile.org/manifest.webapp': '2.2'
            }
        }
        expected = [u'Your language pack contains too many languages. '
                    u'Only one language per pack is supported.']
        with self.assertRaises(ValidationError) as e:
            # The argument to parse() is supposed to be a filename, it doesn't
            # matter here though since we are mocking get_json_data().
            LanguagePackParser().parse('')
        eq_(e.exception.messages, expected)

    @patch('mkt.files.utils.WebAppParser.get_json_data')
    def test_upload_multiple_targets(self, get_json_data_mock):
        get_json_data_mock.return_value = {
            'role': 'langpack',
            'languages-provided': {
                'es': {},
            },
            'languages-target': {
                'app://*.gaiamobile.org/manifest.webapp': '2.2',
                'app://somethingelse.gaiamobile.org/manifest.webapp': '2.3'
            }
        }
        expected = [u'Your language pack contains too many targets. Only one '
                    u'target per pack is supported.']
        with self.assertRaises(ValidationError) as e:
            # The argument to parse() is supposed to be a filename, it doesn't
            # matter here though since we are mocking get_json_data().
            LanguagePackParser().parse('')
        eq_(e.exception.messages, expected)

    @patch('mkt.files.utils.WebAppParser.get_json_data')
    def test_upload_no_role(self, get_json_data_mock):
        get_json_data_mock.return_value = {
            'languages-provided': {
                'es': {}
            },
            'languages-target': {
                'app://*.gaiamobile.org/manifest.webapp': '2.2'
            }
        }
        expected = [u'Your language pack should contain "role": "langpack".']
        with self.assertRaises(ValidationError) as e:
            # The argument to parse() is supposed to be a filename, it doesn't
            # matter here though since we are mocking get_json_data().
            LanguagePackParser().parse('')
        eq_(e.exception.messages, expected)
