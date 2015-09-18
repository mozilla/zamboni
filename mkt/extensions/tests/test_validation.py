# -*- coding: utf-8 -*-
import json

import mock
from nose.tools import eq_
from rest_framework.exceptions import ParseError
from zipfile import ZipFile

from django.core.files.uploadedfile import TemporaryUploadedFile

from mkt.site.tests import TestCase
from mkt.extensions.validation import ExtensionValidator


class TestExtensionValidator(TestCase):
    """
    Tests the ExtensionValidator class. The following methods are tested in
    the TestExtensionViewSetPost test case instead, as part of an end-to-end
    workflow:

    * ExtensionValidator.validate_file
    * ExtensionValidator.validate_json
    """
    def setUp(self):
        self.extension = None
        self.validator = ExtensionValidator()
        super(TestExtensionValidator, self).setUp()

    def tearDown(self):
        if self.extension:
            self.extension.close()

    def _extension(self, data):
        self.extension = TemporaryUploadedFile('ext.zip', 'application/zip', 0,
                                               'UTF-8')
        with ZipFile(self.extension, "w") as z:
            z.writestr('manifest.json', json.dumps(data))
        return self.extension

    def test_full(self):
        extension = self._extension({
            'name': 'My Extension',
            'description': 'This is a valid description',
            'version': '0.1.2.3',
        })
        try:
            ExtensionValidator(extension).validate()
        except ParseError as e:
            assert False, u'Got unexpected validation error: %s' % unicode(e)

    def test_calls(self):
        """
        This method tests that each validation method on ExtensionValidator is
        correctly called. Whenever adding a validation method, take care to
        include its name in the `validation_methods` list.
        """
        validation_methods = [
            'validate_description',
            'validate_file',
            'validate_json',
            'validate_name',
            'validate_version',
        ]
        mocks = {method: mock.DEFAULT for method in validation_methods}
        with mock.patch.multiple(ExtensionValidator, **mocks):
            self.test_full()
            for method in validation_methods:
                mocked = getattr(ExtensionValidator, method)
                eq_(mocked.call_count, 1)

    def test_name_missing(self):
        with self.assertRaises(ParseError):
            self.validator.validate_name({})

    def test_name_not_string(self):
        with self.assertRaises(ParseError):
            self.validator.validate_name({'name': 42})

    def test_name_too_short(self):
        with self.assertRaises(ParseError):
            self.validator.validate_name({'name': ''})

    def test_name_too_long(self):
        with self.assertRaises(ParseError):
            self.validator.validate_name({'name': 'X' * 100})

    def test_name_valid(self):
        NAME = u'My Lîttle Extension'
        try:
            self.validator.validate_name({'name': NAME})
        except:
            assert False, u'A valid name "%s" fails validation' % NAME

    def test_description_valid(self):
        DESC = u'My very lîttle extension has a description'
        try:
            self.validator.validate_description({'description': DESC})
        except:
            assert False, u'A valid description "%s" fails validation' % DESC

    def test_description_missing_valid(self):
        try:
            self.validator.validate_description({})
        except:
            assert False, u'Description should not be required.'

    def test_description_too_long(self):
        with self.assertRaises(ParseError):
            self.validator.validate_name({'name': 'X' * 200})

    def test_version_valid(self):
        VERSION = u'0.42.42.42'
        try:
            self.validator.validate_version({'version': VERSION})
        except:
            assert False, u'A valid version "%s" fails validation' % VERSION

    def test_version_absent(self):
        with self.assertRaises(ParseError):
            self.validator.validate_version({})

    def test_version_not_string(self):
        with self.assertRaises(ParseError):
            self.validator.validate_version({'version': 42})
        with self.assertRaises(ParseError):
            self.validator.validate_version({'version': 0.42})

    def test_version_too_many_dots(self):
        with self.assertRaises(ParseError):
            self.validator.validate_version({'version': '0.42.42.42.42'})

    def test_version_contains_leading_zero(self):
        with self.assertRaises(ParseError):
            self.validator.validate_version({'version': '0.42.042.42'})

    def test_version_contains_hexadecimal_number(self):
        with self.assertRaises(ParseError):
            self.validator.validate_version({'version': '0.42.0x0.42'})

    def test_version_contains_a_non_number(self):
        with self.assertRaises(ParseError):
            self.validator.validate_version({'version': '0.42.x42.42'})

    def test_version_contains_a_negative_number(self):
        with self.assertRaises(ParseError):
            self.validator.validate_version({'version': '0.42.-42.42'})

    def test_version_contains_a_number_too_large(self):
        with self.assertRaises(ParseError):
            self.validator.validate_version({'version': '0.42.65536.42'})
