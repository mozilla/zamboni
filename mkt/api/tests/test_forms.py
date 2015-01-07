import base64

from django.core.exceptions import ValidationError

import mock
from nose.tools import eq_, ok_

import mkt.site.tests
from mkt.api.forms import (PreviewJSONForm, SchemeURLValidator,
                           SluggableModelChoiceField)


class TestPreviewForm(mkt.site.tests.TestCase, mkt.site.tests.MktPaths):

    def setUp(self):
        self.file = base64.b64encode(open(self.mozball_image(), 'r').read())

    def test_bad_type(self):
        form = PreviewJSONForm({'file': {'data': self.file, 'type': 'wtf?'},
                                'position': 1})
        assert not form.is_valid()
        eq_(form.errors['file'], ['Images must be either PNG or JPG.'])

    def test_bad_file(self):
        file_ = base64.b64encode(
            open(self.packaged_app_path('mozball.zip'), 'r').read())
        form = PreviewJSONForm({'file': {'data': file_, 'type': 'image/png'},
                                'position': 1})
        assert not form.is_valid()
        eq_(form.errors['file'], ['Images must be either PNG or JPG.'])

    def test_position_missing(self):
        form = PreviewJSONForm({'file': {'data': self.file,
                                         'type': 'image/jpg'}})
        assert not form.is_valid()
        eq_(form.errors['position'], ['This field is required.'])

    def test_preview(self):
        form = PreviewJSONForm({'file': {'type': '', 'data': ''},
                                'position': 1})
        assert not form.is_valid()
        eq_(form.errors['file'], ['Images must be either PNG or JPG.'])

    def test_not_json(self):
        form = PreviewJSONForm({'file': 1, 'position': 1})
        assert not form.is_valid()
        eq_(form.errors['file'], ['File must be a dictionary.'])

    def test_not_file(self):
        form = PreviewJSONForm({'position': 1})
        assert not form.is_valid()
        eq_(form.errors['file'], ['This field is required.'])


class TestSluggableChoiceField(mkt.site.tests.TestCase):

    def setUp(self):
        self.fld = SluggableModelChoiceField(mock.Mock(),
                                             sluggable_to_field_name='foo')

    def test_nope(self):
        with self.assertRaises(ValueError):
            SluggableModelChoiceField()

    def test_slug(self):
        self.fld.to_python(value='asd')
        ok_(self.fld.to_field_name, 'foo')

    def test_pk(self):
        self.fld.to_python(value='1')
        ok_(self.fld.to_field_name is None)

    def test_else(self):
        self.fld.to_python(value=None)
        ok_(self.fld.to_field_name is None)


class TestSchemeURLValidator(mkt.site.tests.TestCase):
    ftp_url = 'ftp://my-domain.com'
    not_a_url = 'not-a-url'

    def test_url_validator_invalid_url(self):
        with self.assertRaises(ValidationError):
            SchemeURLValidator()(self.not_a_url)

    def test_url_validator_no_schemes(self):
        # Verify we do not see an exception as the URL is valid.
        SchemeURLValidator()(self.ftp_url)

    def test_url_validator_valid_scheme(self):
        # Verify that the URL is still valid when we allow its scheme.
        SchemeURLValidator(schemes=['ftp', 'http'])(self.ftp_url)

    def test_url_validator_invalid_scheme(self):
        with self.assertRaises(ValidationError):
            SchemeURLValidator(schemes=['ftps', 'https'])(self.ftp_url)
