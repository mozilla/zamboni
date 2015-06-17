# -*- coding: utf-8 -*-
import mock
from nose.tools import eq_

import mkt.site.tests
from mkt.submit.helpers import guess_language, string_to_translatedfield_value


strings = {
    'en': 'This string is written in the English language.',
    'it': 'A ogni uccello il suo nido è bello',
    'es': 'Aye caramba',
    'kn': ('ಮನಸ್ಸು ಎಲ್ಲಕ್ಕೂ ಮೂಲ. ಅದನ್ನು ಸರಿಪಡಿಸಿಕೊಳ್ಳದ '
           'ಹೊರತು ಇನ್ನಾವುದೂ ಸರಿಯಾಗದು.')
}


class TestGuessLanguage(mkt.site.tests.TestCase):
    def test_en_high_confidence(self):
        guess = guess_language(strings['en'])
        eq_(guess, 'en')

    def test_it_high_confidence(self):
        guess = guess_language(strings['it'])
        eq_(guess, 'it')

    @mock.patch('mkt.submit.helpers.classify')
    def test_fail(self, mock_classify):
        mock_classify.return_value = 'foo', 0.699
        guess = guess_language(strings['kn'])
        eq_(guess, None)

    @mock.patch('mkt.submit.helpers.classify')
    def test_too_short(self, mock_classify):
        mock_classify.return_value = 'foo', 0.899
        guess = guess_language(strings['es'])
        eq_(guess, None)


class TestStringToTranslatedFieldValue(mkt.site.tests.TestCase):
    def test_high_confidence(self):
        val = string_to_translatedfield_value(strings['it'])
        eq_(val, {'it': strings['it']})

    @mock.patch('mkt.submit.helpers.guess_language')
    def test_low_confidence(self, mock_guess_language):
        mock_guess_language.return_value = None
        val = string_to_translatedfield_value(strings['it'])
        eq_(val, {'en-us': strings['it']})
