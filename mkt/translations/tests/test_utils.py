from django.conf import settings
from django.utils import translation

from nose.tools import eq_

from mkt.site.tests import TestCase
from mkt.translations.models import Translation
from mkt.translations.utils import (find_language, no_translation, to_language,
                                    transfield_changed, truncate,
                                    truncate_text)


class TranslationUtilsTests(TestCase):
    def test_truncate_text(self):
        eq_(truncate_text('foobar', 5), ('...', 0))
        eq_(truncate_text('foobar', 5, True), ('fooba...', 0))
        eq_(truncate_text('foobar', 5, True, 'xxx'), ('foobaxxx', 0))
        eq_(truncate_text('foobar', 6), ('foobar...', 0))
        eq_(truncate_text('foobar', 7), ('foobar', 1))

    def test_truncate(self):
        s = ' <p>one</p><ol><li>two</li><li> three</li> </ol> four <p>five</p>'

        eq_(truncate(s, 100), s)
        eq_(truncate(s, 6), '<p>one</p><ol><li>two...</li></ol>')
        eq_(truncate(s, 5, True), '<p>one</p><ol><li>tw...</li></ol>')
        eq_(truncate(s, 11),
            '<p>one</p><ol><li>two</li><li>three...</li></ol>')
        eq_(truncate(s, 15),
            '<p>one</p><ol><li>two</li><li>three</li></ol>four...')
        eq_(truncate(s, 13, True, 'xxx'),
            '<p>one</p><ol><li>two</li><li>three</li></ol>foxxx')

    def test_transfield_changed(self):
        initial = {
            'some_field': 'some_val',
            'name_en-us': Translation.objects.create(
                id=500, locale='en-us', localized_string='test_name')
        }
        data = {'some_field': 'some_val',
                'name': {'init': '', 'en-us': 'test_name'}}

        # No change.
        eq_(transfield_changed('name', initial, data), 0)

        # Changed localization.
        data['name']['en-us'] = 'test_name_changed'
        eq_(transfield_changed('name', initial, data), 1)

        # New localization.
        data['name']['en-us'] = 'test_name'
        data['name']['en-af'] = Translation.objects.create(
            id=505, locale='en-af', localized_string='test_name_localized')
        eq_(transfield_changed('name', initial, data), 1)

        # Deleted localization.
        del initial['name_en-us']
        eq_(transfield_changed('name', initial, data), 1)

    def test_to_language(self):
        tests = (('en-us', 'en-US'),
                 ('EN-us', 'en-US'),
                 ('en_US', 'en-US'),
                 ('en_us', 'en-US'),
                 ('EN_us', 'en-US'),
                 ('sr-Latn', 'sr-Latn'),
                 ('sr-latn', 'sr-Latn'),
                 ('FR', 'fr'),
                 ('el', 'el'))

        def check(a, b):
            eq_(to_language(a), b)
        for a, b in tests:
            yield check, a, b

    def test_find_language(self):
        tests = (('en-us', 'en-US'),
                 ('en_US', 'en-US'),
                 ('en', 'en-US'),
                 ('sr-latn', 'sr-Latn'),
                 ('sr-Latn', 'sr-Latn'),
                 ('cy', 'cy'),  # A hidden language.
                 ('FR', 'fr'),
                 ('es-ES', None),  # We don't go from specific to generic.
                 ('xxx', None))

        def check(a, b):
            eq_(find_language(a), b)
        for a, b in tests:
            yield check, a, b

    def test_no_translation(self):
        """
        `no_translation` provides a context where only the default
        language is active.
        """
        lang = translation.get_language()
        translation.activate('pt-br')
        with no_translation():
            eq_(translation.get_language(), settings.LANGUAGE_CODE)
        eq_(translation.get_language(), 'pt-br')
        with no_translation('es'):
            eq_(translation.get_language(), 'es')
        eq_(translation.get_language(), 'pt-br')
        translation.activate(lang)
