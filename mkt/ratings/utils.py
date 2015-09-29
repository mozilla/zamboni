import string

import langid

# Determined by examining review corpus and confidence levels produced by
# langid, 18 May 2015. See bug 875455 for details.
COMMON_REVIEW_WORDS = {
    'bom': 'pt',
    'buena': 'es',
    'bueno': 'es',
    'cool': 'en',
    'esta': 'es',
    'excelente': 'es',
    'good': 'en',
    'great': 'en',
    'gusta': 'es',
    'muito': 'pt',
    'muy': 'es',
    'nice': 'en',
    'ok': 'en',
    'super': 'en',
    'the': 'en',
    'very': 'en'
}


def guess_language(text):
    guessed_lang, confidence = langid.classify(text)
    if confidence < 0.9:
        depunct = dict.fromkeys([ord(c) for c in string.punctuation], u' ')
        words = text.lower().translate(depunct).split()
        assumed_lang = None
        for w in words:
            assumed_lang = COMMON_REVIEW_WORDS.get(w)
            if assumed_lang:
                break
        if assumed_lang is None and len(words) <= 3:
            # Too little text to reliably guess.
            return None
        return assumed_lang or guessed_lang
    return guessed_lang
