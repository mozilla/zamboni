import contextlib

from django.conf import settings
from django.utils import translation
from django.utils.encoding import force_unicode

import html5lib
import jinja2
from babel import Locale
from html5lib.serializer.htmlserializer import HTMLSerializer


# Copypaste from Jinja2 2.7.2. The behaviour change in 2.8 may be more
# desirable but this matches our existing tests.
def do_truncate(s, length=255, killwords=False, end='...'):
    if len(s) <= length:
        return s
    elif killwords:
        return s[:length] + end
    words = s.split(' ')
    result = []
    m = 0
    for word in words:
        m += len(word) + 1
        if m > length:
            break
        result.append(word)
    result.append(end)
    return u' '.join(result)


def truncate_text(text, limit, killwords=False, end='...'):
    """Return as many characters as possible without going over the limit.

    Return the truncated text and the characters left before the limit, if any.

    """
    text = text.strip()
    text_length = len(text)

    if text_length < limit:
        return text, limit - text_length

    # Explicitly add "end" in any case, as Jinja can't know we're truncating
    # for real here, even though we might be at the end of a word.
    text = do_truncate(text, limit, killwords, end='')
    return text + end, 0


def trim(tree, limit, killwords, end):
    """Truncate the text of an html5lib tree."""
    if tree.text:  # Root node's text.
        tree.text, limit = truncate_text(tree.text, limit, killwords, end)
    for child in tree:  # Immediate children.
        if limit <= 0:
            # We reached the limit, remove all remaining children.
            tree.remove(child)
        else:
            # Recurse on the current child.
            _parsed_tree, limit = trim(child, limit, killwords, end)
    if tree.tail:  # Root node's tail text.
        if limit <= 0:
            tree.tail = ''
        else:
            tree.tail, limit = truncate_text(tree.tail, limit, killwords, end)
    return tree, limit


def text_length(tree):
    """Find the length of the text content, excluding markup."""
    total = 0
    for node in tree.getiterator():  # Traverse all the tree nodes.
        # In etree, a node has a text and tail attribute.
        # Eg: "<b>inner text</b> tail text <em>inner text</em>".
        if node.text:
            total += len(node.text.strip())
        if node.tail:
            total += len(node.tail.strip())
    return total


def truncate(html, length, killwords=False, end='...'):
    """
    Return a slice of ``html`` <= length chars.

    killwords and end are currently ignored.

    ONLY USE FOR KNOWN-SAFE HTML.
    """
    tree = html5lib.parseFragment(html)
    if text_length(tree) <= length:
        return jinja2.Markup(html)
    else:
        # Get a truncated version of the tree.
        short, _ = trim(tree, length, killwords, end)

        # Serialize the parsed tree back to html.
        walker = html5lib.treewalkers.getTreeWalker('etree')
        stream = walker(short)
        serializer = html5lib.serializer.htmlserializer.HTMLSerializer(
            quote_attr_values=True, omit_optional_tags=False)
        return jinja2.Markup(force_unicode(serializer.render(stream)))


def transfield_changed(field, initial, data):
    """
    For forms, compares initial data against cleaned_data for TransFields.
    Returns True if data is the same. Returns False if data is different.

    Arguments:
    field -- name of the form field as-is.
    initial -- data in the form of {'description_en-us': 'x',
                                    'description_en-br': 'y'}
    data -- cleaned data in the form of {'description': {'init': '',
                                                         'en-us': 'x',
                                                         'en-br': 'y'}
    """
    initial = [(k, v.localized_string) for k, v in initial.iteritems()
               if '%s_' % field in k and v is not None]
    data = [('%s_%s' % (field, k), v) for k, v in data[field].iteritems()
            if k != 'init']
    return set(initial) != set(data)


def to_language(locale):
    """Like django's to_language, but en_us or en-us comes out as en-US."""
    if '_' in locale:
        # We have a locale, and it has an underscore. We get django to
        # transform it to a language for us, which will lowercase it and
        # replace the underscore with a dash, and then call this function
        # (yay recursion).
        return to_language(translation.trans_real.to_language(locale))
    elif '-' in locale:
        # We have something that already looks like a language, with a dash,
        # but we want the region to always be uppercase.
        lang, region = locale.lower().split('-')

        # Special case: Latn isn't really a region, it's an alphabet. If we
        # find it, don't uppercase it, capitalize it, to match the languages
        # we have defined such as sr-Latn.
        if region == 'latn':
            region = region.capitalize()
        else:
            region = region.upper()
        return '%s-%s' % (lang, region)
    else:
        # Just a locale with no underscore, let django do its job.
        return translation.trans_real.to_language(locale)


def get_locale_from_lang(lang):
    """Pass in a language (u'en-US') get back a Locale object courtesy of
    Babel.  Use this to figure out currencies, bidi, names, etc."""
    # Special fake language can just act like English for formatting and such
    if not lang or lang == 'dbg':
        lang = 'en'
    return Locale(translation.to_locale(lang))


@contextlib.contextmanager
def no_translation(lang=None):
    """
    Activate the settings lang, or lang provided, while in context.
    """
    old_lang = translation.trans_real.get_language()
    if lang:
        translation.trans_real.activate(lang)
    else:
        translation.trans_real.deactivate()
    yield
    translation.trans_real.activate(old_lang)


def find_language(locale):
    """
    Return a locale we support, or None.
    """
    if not locale:
        return None

    LANGS = settings.AMO_LANGUAGES

    if locale in LANGS:
        return locale

    # Check if locale has a short equivalent.
    loc = settings.SHORTER_LANGUAGES.get(locale)
    if loc:
        return loc

    # Check if locale is something like en_US that needs to be converted.
    locale = to_language(locale)
    if locale in LANGS:
        return locale

    return None


def clean_nl(string):
    """
    This will clean up newlines so that nl2br can properly be called on the
    cleaned text.
    """

    html_blocks = ['{http://www.w3.org/1999/xhtml}blockquote',
                   '{http://www.w3.org/1999/xhtml}ol',
                   '{http://www.w3.org/1999/xhtml}li',
                   '{http://www.w3.org/1999/xhtml}ul']

    if not string:
        return string

    def parse_html(tree):
        # In etree, a tag may have:
        # - some text content (piece of text before its first child)
        # - a tail (piece of text just after the tag, and before a sibling)
        # - children
        # Eg: "<div>text <b>children's text</b> children's tail</div> tail".

        # Strip new lines directly inside block level elements: first new lines
        # from the text, and:
        # - last new lines from the tail of the last child if there's children
        #   (done in the children loop below).
        # - or last new lines from the text itself.
        if tree.tag in html_blocks:
            if tree.text:
                tree.text = tree.text.lstrip('\n')
                if not len(tree):  # No children.
                    tree.text = tree.text.rstrip('\n')

            # Remove the first new line after a block level element.
            if tree.tail and tree.tail.startswith('\n'):
                tree.tail = tree.tail[1:]

        for child in tree:  # Recurse down the tree.
            if tree.tag in html_blocks:
                # Strip new lines directly inside block level elements: remove
                # the last new lines from the children's tails.
                if child.tail:
                    child.tail = child.tail.rstrip('\n')
            parse_html(child)
        return tree

    parse = parse_html(html5lib.parseFragment(string))

    # Serialize the parsed tree back to html.
    walker = html5lib.treewalkers.getTreeWalker('etree')
    stream = walker(parse)
    serializer = HTMLSerializer(quote_attr_values=True,
                                omit_optional_tags=False)
    return serializer.render(stream)
