from rest_framework.exceptions import ParseError

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
        self.validator = ExtensionValidator()
        super(TestExtensionValidator, self).setUp()

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
