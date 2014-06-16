from django.forms import ModelForm

from nose.tools import eq_
from pyquery import PyQuery as pq

import amo.tests
from mkt.translations import forms, fields
from mkt.translations.tests.testapp.models import TranslatedModel


class TestForm(forms.TranslationFormMixin, ModelForm):
    name = fields.TransField()
    class Meta:
        model = TranslatedModel


class TestTranslationFormMixin(amo.tests.TestCase):

    def test_default_locale(self):
        obj = TranslatedModel()
        obj.get_fallback = lambda: 'pl'

        f = TestForm(instance=obj)
        eq_(f.fields['name'].default_locale, 'pl')
        eq_(f.fields['name'].widget.default_locale, 'pl')
        eq_(pq(f.as_p())('input:not([lang=init])').attr('lang'), 'pl')
