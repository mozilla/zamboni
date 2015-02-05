# -*- coding: utf-8 -*-
from django.forms import ValidationError

from mock import patch
from nose.tools import eq_

from mkt.files.tests.test_utils_ import TestWebAppParser
from mkt.langpacks.utils import LanguagePackParser


class TestLangPackUpload(TestWebAppParser):
    klass = LanguagePackParser
    base_mock_data = {
        'name': 'Blah',
        'developer': {
            'name': 'Mozilla Marketplace Testing'
        },
        'role': 'langpack',
        'version': '0.1',
        'languages-provided': {
            'de': {},
        },
        'languages-target': {
            'app://*.gaiamobile.org/manifest.webapp': '2.2'
        }
    }

    @patch('mkt.files.utils.WebAppParser.get_json_data')
    def test_upload_multiple_languages(self, get_json_data_mock):
        get_json_data_mock.return_value = self.build_data_mock({
            'languages-provided': {
                'es': {},
                'de': {},
            }
        })
        expected = [u'Your language pack contains too many languages. '
                    u'Only one language per pack is supported.']
        with self.assertRaises(ValidationError) as e:
            # The argument to parse() is supposed to be a filename, it doesn't
            # matter here though since we are mocking get_json_data().
            self.klass().parse('')
        eq_(e.exception.messages, expected)

    @patch('mkt.files.utils.WebAppParser.get_json_data')
    def test_upload_multiple_targets(self, get_json_data_mock):
        get_json_data_mock.return_value = self.build_data_mock({
            'languages-target': {
                'app://*.gaiamobile.org/manifest.webapp': '2.2',
                'app://somethingelse.gaiamobile.org/manifest.webapp': '2.3'
            }
        })
        expected = [u'Your language pack contains too many targets. Only one '
                    u'target per pack is supported.']
        with self.assertRaises(ValidationError) as e:
            # The argument to parse() is supposed to be a filename, it doesn't
            # matter here though since we are mocking get_json_data().
            self.klass().parse('')
        eq_(e.exception.messages, expected)

    @patch('mkt.files.utils.WebAppParser.get_json_data')
    def test_upload_no_role(self, get_json_data_mock):
        get_json_data_mock.return_value = self.build_data_mock()
        del get_json_data_mock.return_value['role']
        expected = [u'Your language pack should contain "role": "langpack".']
        with self.assertRaises(ValidationError) as e:
            # The argument to parse() is supposed to be a filename, it doesn't
            # matter here though since we are mocking get_json_data().
            self.klass().parse('')
        eq_(e.exception.messages, expected)

    @patch('mkt.files.utils.WebAppParser.get_json_data')
    def test_upload_version_missing(self, get_json_data_mock):
        get_json_data_mock.return_value = self.build_data_mock()
        del get_json_data_mock.return_value['version']
        expected = [u'Your language pack should contain a version.']
        with self.assertRaises(ValidationError) as e:
            self.klass().parse('')
        eq_(e.exception.messages, expected)

    @patch('mkt.files.utils.WebAppParser.get_json_data')
    def test_homescreen_role(self, get_json_data_mock):
        # Parent class also have this test, we are overriding it since
        # homescreen apps are not valid langpacks.
        get_json_data_mock.return_value = self.build_data_mock()
        get_json_data_mock.return_value['role'] = 'homescreen'
        expected = [u'Your language pack should contain "role": "langpack".']
        with self.assertRaises(ValidationError) as e:
            # The argument to parse() is supposed to be a filename, it doesn't
            # matter here though since we are mocking get_json_data().
            self.klass().parse('')
        eq_(e.exception.messages, expected)

    def test_langpack_role(self):
        # Parent class has this test, but we don't want it here.
        pass
