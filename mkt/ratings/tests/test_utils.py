# -*- coding: utf-8 -*-
from nose.tools import eq_
import mkt.site.tests
from mkt.ratings.utils import guess_language


class LanguageGuessTest(mkt.site.tests.TestCase):

    def test_keyword(self):
        eq_(guess_language(u'Muy bien'), 'es')
        eq_(guess_language(u'Muito bom o jogo!'), 'pt')
        eq_(guess_language(u'pretty good. :D'), 'en')

    def test_langid(self):
        eq_(guess_language(u'I thought it had no texture.'), 'en')
        eq_(guess_language(
            u'Je peux manger du verre, cela ne me fait pas mal'), 'fr')
        eq_(guess_language(u'На всех не угоди́шь'), 'ru')
        eq_(guess_language(u'角を矯めて牛を殺す'), 'ja')
        eq_(guess_language(u'您要点什么'), 'zh')
        eq_(guess_language(
            u'Esta muy bien este juego, se lo recomiendo a todos'), 'es')
        eq_(guess_language(
            u'Esperimentem que vocês irão aprovar tambem!'), 'pt')

    def test_unidentifiable(self):
        eq_(guess_language(u'Like it'), None)
        eq_(guess_language(u'dsfksadflkj'), None)
        eq_(guess_language(u'exelente'), None)
