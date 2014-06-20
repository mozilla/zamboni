# -*- coding: utf-8 -*-
import mimetypes
import os
from datetime import datetime, timedelta
from urlparse import urljoin

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile

import jingo
from mock import patch
from nose.tools import eq_

import amo
import amo.tests
from amo import urlresolvers, utils, helpers
from amo.utils import ImageCheck


def render(s, context={}):
    t = jingo.env.from_string(s)
    return t.render(context)


def test_strip_controls():
    # We want control codes like \x0c to disappear.
    eq_('I ove you', helpers.strip_controls('I \x0cove you'))


def test_finalize():
    """We want None to show up as ''.  We do this in JINJA_CONFIG."""
    eq_('', render('{{ x }}', {'x': None}))


def test_slugify_spaces():
    """We want slugify to preserve spaces, but not at either end."""
    eq_(utils.slugify(' b ar '), 'b-ar')
    eq_(utils.slugify(' b ar ', spaces=True), 'b ar')
    eq_(utils.slugify(' b  ar ', spaces=True), 'b  ar')


@patch('amo.helpers.urlresolvers.reverse')
def test_url(mock_reverse):
    render('{{ url("viewname", 1, z=2) }}')
    mock_reverse.assert_called_with('viewname', args=(1,), kwargs={'z': 2},
                                    add_prefix=True)

    render('{{ url("viewname", 1, z=2, host="myhost") }}')
    mock_reverse.assert_called_with('viewname', args=(1,), kwargs={'z': 2},
                                    add_prefix=True)


def test_url_src():
    s = render('{{ url("addons.detail", "a3615", src="xxx") }}')
    assert s.endswith('?src=xxx')


def test_urlparams():
    url = '/en-US/firefox/search-tools/category'
    c = {'base': url,
         'base_frag': url + '#hash',
         'base_query': url + '?x=y',
         'sort': 'name', 'frag': 'frag'}

    # Adding a query.
    s = render('{{ base_frag|urlparams(sort=sort) }}', c)
    eq_(s, '%s?sort=name#hash' % url)

    # Adding a fragment.
    s = render('{{ base|urlparams(frag) }}', c)
    eq_(s, '%s#frag' % url)

    # Replacing a fragment.
    s = render('{{ base_frag|urlparams(frag) }}', c)
    eq_(s, '%s#frag' % url)

    # Adding query and fragment.
    s = render('{{ base_frag|urlparams(frag, sort=sort) }}', c)
    eq_(s, '%s?sort=name#frag' % url)

    # Adding query with existing params.
    s = render('{{ base_query|urlparams(frag, sort=sort) }}', c)
    eq_(s, '%s?sort=name&amp;x=y#frag' % url)

    # Replacing a query param.
    s = render('{{ base_query|urlparams(frag, x="z") }}', c)
    eq_(s, '%s?x=z#frag' % url)

    # Params with value of None get dropped.
    s = render('{{ base|urlparams(sort=None) }}', c)
    eq_(s, url)

    # Removing a query
    s = render('{{ base_query|urlparams(x=None) }}', c)
    eq_(s, url)


def test_urlparams_unicode():
    url = u'/xx?evil=reco\ufffd\ufffd\ufffd\u02f5'
    utils.urlparams(url)


def test_isotime():
    time = datetime(2009, 12, 25, 10, 11, 12)
    s = render('{{ d|isotime }}', {'d': time})
    eq_(s, '2009-12-25T18:11:12Z')
    s = render('{{ d|isotime }}', {'d': None})
    eq_(s, '')


def test_epoch():
    time = datetime(2009, 12, 25, 10, 11, 12)
    s = render('{{ d|epoch }}', {'d': time})
    eq_(s, '1261764672')
    s = render('{{ d|epoch }}', {'d': None})
    eq_(s, '')


def test_external_url():
    redirect_url = settings.REDIRECT_URL
    secretkey = settings.REDIRECT_SECRET_KEY
    settings.REDIRECT_URL = 'http://example.net'
    settings.REDIRECT_SECRET_KEY = 'sekrit'

    try:
        myurl = 'http://example.com'
        s = render('{{ "%s"|external_url }}' % myurl)
        eq_(s, urlresolvers.get_outgoing_url(myurl))
    finally:
        settings.REDIRECT_URL = redirect_url
        settings.REDIRECT_SECRET_KEY = secretkey


@patch('amo.helpers.urlresolvers.get_outgoing_url')
def test_linkify_bounce_url_callback(mock_get_outgoing_url):
    mock_get_outgoing_url.return_value = 'bar'

    res = urlresolvers.linkify_bounce_url_callback({'href': 'foo'})

    # Make sure get_outgoing_url was called.
    eq_(res, {'href': 'bar'})
    mock_get_outgoing_url.assert_called_with('foo')


@patch('amo.helpers.urlresolvers.linkify_bounce_url_callback')
def test_linkify_with_outgoing_text_links(mock_linkify_bounce_url_callback):
    def side_effect(attrs, new=False):
        attrs['href'] = 'bar'
        return attrs

    mock_linkify_bounce_url_callback.side_effect = side_effect

    # Without nofollow.
    res = urlresolvers.linkify_with_outgoing('a text http://example.com link',
                                             nofollow=False)
    eq_(res, 'a text <a href="bar">http://example.com</a> link')

    # With nofollow (default).
    res = urlresolvers.linkify_with_outgoing('a text http://example.com link')
    eq_(res, 'a text <a rel="nofollow" href="bar">http://example.com</a> link')

    res = urlresolvers.linkify_with_outgoing('a text http://example.com link',
                                             nofollow=True)
    eq_(res, 'a text <a rel="nofollow" href="bar">http://example.com</a> link')


@patch('amo.helpers.urlresolvers.linkify_bounce_url_callback')
def test_linkify_with_outgoing_markup_links(mock_linkify_bounce_url_callback):
    def side_effect(attrs, new=False):
        attrs['href'] = 'bar'
        return attrs

    mock_linkify_bounce_url_callback.side_effect = side_effect

    # Without nofollow.
    res = urlresolvers.linkify_with_outgoing(
        'a markup <a href="http://example.com">link</a> with text',
        nofollow=False)
    eq_(res, 'a markup <a href="bar">link</a> with text')

    # With nofollow (default).
    res = urlresolvers.linkify_with_outgoing(
        'a markup <a href="http://example.com">link</a> with text')
    eq_(res, 'a markup <a rel="nofollow" href="bar">link</a> with text')

    res = urlresolvers.linkify_with_outgoing(
        'a markup <a href="http://example.com">link</a> with text',
        nofollow=True)
    eq_(res, 'a markup <a rel="nofollow" href="bar">link</a> with text')


def get_image_path(name):
    return os.path.join(settings.ROOT, 'apps', 'amo', 'tests', 'images', name)


def get_uploaded_file(name):
    data = open(get_image_path(name)).read()
    return SimpleUploadedFile(name, data,
                              content_type=mimetypes.guess_type(name)[0])


class TestAnimatedImages(amo.tests.TestCase):

    def test_animated_images(self):
        img = ImageCheck(open(get_image_path('animated.png')))
        assert img.is_animated()
        img = ImageCheck(open(get_image_path('non-animated.png')))
        assert not img.is_animated()

        img = ImageCheck(open(get_image_path('animated.gif')))
        assert img.is_animated()
        img = ImageCheck(open(get_image_path('non-animated.gif')))
        assert not img.is_animated()

    def test_junk(self):
        img = ImageCheck(open(__file__, 'rb'))
        assert not img.is_image()
        img = ImageCheck(open(get_image_path('non-animated.gif')))
        assert img.is_image()


def test_jinja_trans_monkeypatch():
    # This tests the monkeypatch in manage.py that prevents localizers from
    # taking us down.
    render('{% trans come_on=1 %}% (come_on)s{% endtrans %}')
    render('{% trans come_on=1 %}%(come_on){% endtrans %}')
    render('{% trans come_on=1 %}%(come_on)z{% endtrans %}')


def test_absolutify():
    eq_(helpers.absolutify('/woo'), urljoin(settings.SITE_URL, '/woo'))
    eq_(helpers.absolutify('https://addons.mozilla.org'),
        'https://addons.mozilla.org')


def test_timesince():
    month_ago = datetime.now() - timedelta(days=30)
    eq_(helpers.timesince(month_ago), u'1 month ago')
    eq_(helpers.timesince(None), u'')


def test_f():
    # This makes sure there's no UnicodeEncodeError when doing the string
    # interpolation.
    eq_(render(u'{{ "foo {0}"|f("baré") }}'), u'foo baré')
