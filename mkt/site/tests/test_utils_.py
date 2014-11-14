from os import path

from django.conf import settings

from mock import patch
from nose.tools import assert_not_equal, eq_, ok_

import amo.tests
from amo.utils import ImageCheck
from mkt.site.utils import (get_outgoing_url, linkify_bounce_url_callback,
                            linkify_with_outgoing)

def test_outgoing_url():
    redirect_url = settings.REDIRECT_URL
    secretkey = settings.REDIRECT_SECRET_KEY
    exceptions = settings.REDIRECT_URL_WHITELIST
    settings.REDIRECT_URL = 'http://example.net'
    settings.REDIRECT_SECRET_KEY = 'sekrit'
    settings.REDIRECT_URL_WHITELIST = ['nicedomain.com']

    try:
        myurl = 'http://example.com'
        s = get_outgoing_url(myurl)

        # Regular URLs must be escaped.
        eq_(s,
            'http://example.net/bc7d4bb262c9f0b0f6d3412ede7d3252c2e311bb1d55f6'
            '2315f636cb8a70913b/'
            'http%3A//example.com')

        # No double-escaping of outgoing URLs.
        s2 = get_outgoing_url(s)
        eq_(s, s2)

        evil = settings.REDIRECT_URL.rstrip('/') + '.evildomain.com'
        s = get_outgoing_url(evil)
        assert_not_equal(s, evil,
                         'No subdomain abuse of double-escaping protection.')

        nice = 'http://nicedomain.com/lets/go/go/go'
        eq_(nice, get_outgoing_url(nice))

    finally:
        settings.REDIRECT_URL = redirect_url
        settings.REDIRECT_SECRET_KEY = secretkey
        settings.REDIRECT_URL_WHITELIST = exceptions


def test_outgoing_url_dirty_unicode():
    bad = (u'http://chupakabr.ru/\u043f\u0440\u043e\u0435\u043a\u0442\u044b/'
           u'\u043c\u0443\u0437\u044b\u043a\u0430-vkontakteru/')
    get_outgoing_url(bad)  # bug 564057


def test_outgoing_url_query_params():
    url = 'http://xx.com?q=1&v=2'
    fixed = get_outgoing_url(url)
    assert fixed.endswith('http%3A//xx.com%3Fq=1&v=2'), fixed

    url = 'http://xx.com?q=1&amp;v=2'
    fixed = get_outgoing_url(url)
    assert fixed.endswith('http%3A//xx.com%3Fq=1&v=2'), fixed

    # Check XSS vectors.
    url = 'http://xx.com?q=1&amp;v=2" style="123"'
    fixed = get_outgoing_url(url)
    assert fixed.endswith('%3A//xx.com%3Fq=1&v=2%22%20style=%22123%22'), fixed


@patch('mkt.site.utils.get_outgoing_url')
def test_linkify_bounce_url_callback(mock_get_outgoing_url):
    mock_get_outgoing_url.return_value = 'bar'

    res = linkify_bounce_url_callback({'href': 'foo'})

    # Make sure get_outgoing_url was called.
    eq_(res, {'href': 'bar'})
    mock_get_outgoing_url.assert_called_with('foo')


@patch('mkt.site.utils.linkify_bounce_url_callback')
def test_linkify_with_outgoing_text_links(mock_linkify_bounce_url_callback):
    def side_effect(attrs, new=False):
        attrs['href'] = 'bar'
        return attrs

    mock_linkify_bounce_url_callback.side_effect = side_effect

    # Without nofollow.
    res = linkify_with_outgoing('a text http://example.com link', nofollow=False)
    eq_(res, 'a text <a href="bar">http://example.com</a> link')

    # With nofollow (default).
    res = linkify_with_outgoing('a text http://example.com link')
    ok_(res in [
        'a text <a rel="nofollow" href="bar">http://example.com</a> link',
        'a text <a href="bar" rel="nofollow">http://example.com</a> link'])

    res = linkify_with_outgoing('a text http://example.com link', nofollow=True)
    ok_(res in [
        'a text <a rel="nofollow" href="bar">http://example.com</a> link',
        'a text <a href="bar" rel="nofollow">http://example.com</a> link'])


@patch('mkt.site.utils.linkify_bounce_url_callback')
def test_linkify_with_outgoing_markup_links(mock_linkify_bounce_url_callback):
    def side_effect(attrs, new=False):
        attrs['href'] = 'bar'
        return attrs

    mock_linkify_bounce_url_callback.side_effect = side_effect

    # Without nofollow.
    res = linkify_with_outgoing(
        'a markup <a href="http://example.com">link</a> with text',
        nofollow=False)
    eq_(res, 'a markup <a href="bar">link</a> with text')

    # With nofollow (default).
    res = linkify_with_outgoing(
        'a markup <a href="http://example.com">link</a> with text')
    ok_(res in ['a markup <a rel="nofollow" href="bar">link</a> with text',
                'a markup <a href="bar" rel="nofollow">link</a> with text'])

    res = linkify_with_outgoing(
        'a markup <a href="http://example.com">link</a> with text',
        nofollow=True)
    ok_(res in ['a markup <a rel="nofollow" href="bar">link</a> with text',
                'a markup <a href="bar" rel="nofollow">link</a> with text'])


def get_image_path(name):
    return path.join(settings.ROOT, 'apps', 'amo', 'tests', 'images', name)


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
