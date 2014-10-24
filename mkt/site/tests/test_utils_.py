from django.conf import settings

from nose.tools import eq_, assert_not_equal

from mkt.site.utils import get_outgoing_url


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
