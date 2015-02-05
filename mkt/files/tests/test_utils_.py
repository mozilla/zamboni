from copy import deepcopy

from django import forms

import mock
from nose.tools import eq_, ok_

import mkt.site.tests
from mkt.files.utils import WebAppParser


class TestWebAppParser(mkt.site.tests.TestCase):
    klass = WebAppParser
    base_mock_data = {
        'name': 'Blah',
        'developer': {
            'name': 'Mozilla Marketplace Testing'
        }
    }

    def build_data_mock(self, extra_data=None):
        data = {}
        data.update(self.base_mock_data)
        if extra_data is not None:
            data.update(extra_data)
        # deepcopy data dict so that we can modify dicts inside it.
        return deepcopy(data)

    @mock.patch('mkt.files.utils.WebAppParser.get_json_data')
    def test_langpack_role(self, get_json_data):
        get_json_data.return_value = self.build_data_mock({
            'role': 'langpack'
        })
        with self.assertRaises(forms.ValidationError) as e:
            # The argument to parse() is supposed to be a filename, it doesn't
            # matter here though since we are mocking get_json_data().
            self.klass().parse('')
        eq_(e.exception.messages,
            [u'The "langpack" role is invalid for Web Apps. Please submit'
             u' this app as a language pack instead.'])

    @mock.patch('mkt.files.utils.WebAppParser.get_json_data')
    def test_homescreen_role(self, get_json_data):
        get_json_data.return_value = self.build_data_mock({
            'role': 'homescreen'
        })
        # The argument to parse() is supposed to be a filename, it doesn't
        # matter here though since we are mocking get_json_data().
        ok_(self.klass().parse(''))

    @mock.patch('mkt.files.utils.WebAppParser.get_json_data')
    def test_no_developer_name(self, get_json_data):
        data = self.build_data_mock()
        del data['developer']
        get_json_data.return_value = data
        with self.assertRaises(forms.ValidationError) as e:
            # The argument to parse() is supposed to be a filename, it doesn't
            # matter here though since we are mocking get_json_data().
            self.klass().parse('')
        eq_(e.exception.messages, ["Developer name is required in the manifest"
                                   " in order to display it on the app's "
                                   "listing."])

    @mock.patch('mkt.files.utils.WebAppParser.get_json_data')
    def test_empty_developer_object(self, get_json_data):
        data = self.build_data_mock()
        del data['developer']['name']
        get_json_data.return_value = data
        with self.assertRaises(forms.ValidationError) as e:
            # The argument to parse() is supposed to be a filename, it doesn't
            # matter here though since we are mocking get_json_data().
            self.klass().parse('')
        eq_(e.exception.messages, ["Developer name is required in the manifest"
                                   " in order to display it on the app's "
                                   "listing."])

    @mock.patch('mkt.files.utils.WebAppParser.get_json_data')
    def test_developer_name(self, get_json_data):
        get_json_data.return_value = self.build_data_mock()
        # The argument to parse() is supposed to be a filename, it doesn't
        # matter here though since we are mocking get_json_data().
        parsed_results = self.klass().parse('')
        eq_(parsed_results['developer_name'], 'Mozilla Marketplace Testing')

    @mock.patch('mkt.files.utils.WebAppParser.get_json_data')
    def test_name_with_translations(self, get_json_data):
        get_json_data.return_value = self.build_data_mock({
            'default_locale': 'en-US',
            'locales': {
                'fr': {
                    'name': 'Blah (fr)',
                },
                'es': {
                    'name': 'Blah (es)',
                }
            }
        })
        # The argument to parse() is supposed to be a filename, it doesn't
        # matter here though since we are mocking get_json_data().
        parsed_results = self.klass().parse('')
        eq_(parsed_results['name'].get('fr'), 'Blah (fr)')
        eq_(parsed_results['name'].get('es'), 'Blah (es)')
        eq_(parsed_results['name'].get('en-US'), 'Blah')
        eq_(parsed_results['name'].get('de'), None)
        eq_(parsed_results['default_locale'], 'en-US')

    @mock.patch('mkt.files.utils.WebAppParser.get_json_data')
    def test_name_with_translations_and_short_languages(self, get_json_data):
        get_json_data.return_value = self.build_data_mock({
            'default_locale': 'en',  # Will be transformed to en-US.
            'locales': {
                'fr': {
                    'name': 'Blah (fr)',
                },
                'pt': {
                    'name': 'Blah (pt)',
                }
            }
        })
        # The argument to parse() is supposed to be a filename, it doesn't
        # matter here though since we are mocking get_json_data().
        parsed_results = self.klass().parse('')
        eq_(parsed_results['name'].get('fr'), 'Blah (fr)')
        eq_(parsed_results['name'].get('pt-PT'), 'Blah (pt)')
        eq_(parsed_results['name'].get('en-US'), 'Blah')
        eq_(parsed_results['name'].get('de'), None)
        eq_(parsed_results['name'].get('pt'), None)
        eq_(parsed_results['name'].get('en'), None)
        eq_(parsed_results['default_locale'], 'en-US')

    @mock.patch('mkt.files.utils.WebAppParser.get_json_data')
    def test_name_with_translations_and_weird_format(self, get_json_data):
        get_json_data.return_value = self.build_data_mock({
            'default_locale': 'PT-br',  # Will be transformed to pt-BR
            'locales': {
                'fr': {
                    'name': 'Blah (fr)',
                },
                'pt': {
                    'name': 'Blah (pt)',
                }
            }
        })
        # The argument to parse() is supposed to be a filename, it doesn't
        # matter here though since we are mocking get_json_data().
        parsed_results = self.klass().parse('')
        eq_(parsed_results['default_locale'], 'pt-BR')
        eq_(parsed_results['name'].get('fr'), 'Blah (fr)')
        eq_(parsed_results['name'].get('pt-PT'), 'Blah (pt)')
        eq_(parsed_results['name'].get('pt-BR'), 'Blah')
        eq_(parsed_results['name'].get('de'), None)
        eq_(parsed_results['name'].get('pt'), None)
        eq_(parsed_results['name'].get('en'), None)

    @mock.patch('mkt.files.utils.WebAppParser.get_json_data')
    def test_name_with_translations_fallback(self, get_json_data):
        get_json_data.return_value = self.build_data_mock({
            'description': 'Blah Description',
            'default_locale': 'en-US',
            'locales': {
                'fr': {
                    'description': 'Blah Description (fr)',
                },
                'es': {
                    'name': 'Blah (es)',
                }
            }
        })
        # The argument to parse() is supposed to be a filename, it doesn't
        # matter here though since we are mocking get_json_data().
        parsed_results = self.klass().parse('')
        eq_(parsed_results['name'].get('fr'), 'Blah')  # Falls back to default.
        eq_(parsed_results['name'].get('es'), 'Blah (es)')
        eq_(parsed_results['name'].get('en-US'), 'Blah')
        eq_(parsed_results['name'].get('de'), None)
        eq_(parsed_results['default_locale'], 'en-US')
