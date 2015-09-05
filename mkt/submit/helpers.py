import re

import jinja2
from jingo import register, env
from langid import classify

from django.conf import settings

import mkt
from mkt.submit.models import AppSubmissionChecklist
from mkt.translations.utils import find_language


def del_by_key(data, delete):
    """Delete a tuple from a list of tuples based on its first item."""
    data = list(data)
    for idx, item in enumerate(data):
        if ((isinstance(item[0], basestring) and item[0] == delete) or
                (isinstance(item[0], (list, tuple)) and item[0] in delete)):
            del data[idx]
    return data


@register.function
def progress(request, webapp, step):
    steps = list(mkt.APP_STEPS)

    completed = []

    # TODO: Hide "Developer Account" step if user already read Dev Agreement.
    # if request.user.read_dev_agreement:
    #    steps = del_by_key(steps, 'terms')

    if webapp:
        try:
            completed = webapp.appsubmissionchecklist.get_completed()
        except AppSubmissionChecklist.DoesNotExist:
            pass

    # We don't yet have a checklist yet if we just read the Dev Agreement.
    if not completed and step and step != 'terms':
        completed = ['terms']

    c = dict(steps=steps, current=step, completed=completed)
    t = env.get_template('submit/helpers/progress.html').render(c)
    return jinja2.Markup(t)


def guess_language(text):
    """
    Passed a string, returns a two-tuple indicating the language of that
    string, and the confidence on a 0-1.0 scale.

    If the confidence is below 0.7, or below 0.9 in a string of 3 words or
    less, will return None.
    """
    guess, confidence = classify(text)
    if confidence < 0.7:
        return None
    elif confidence < 0.9:
        word_count = len(re.findall(r"[\w']+", text))
        if word_count <= 3:
            return None
    return guess


def string_to_translatedfield_value(text):
    """
    Passed a string, will return a dict mapping 'language': string, suitable to
    be assigned to the value of a TranslatedField. If the language can not be
    determined with confidence, will assume English.
    """
    guess = guess_language(text)
    if guess:
        lang = find_language(guess).lower()
        if lang:
            return {lang: text}
    return {settings.SHORTER_LANGUAGES['en'].lower(): text}
