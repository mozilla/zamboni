#-*- coding: utf-8 -*-
import hashlib
import hmac
import urllib
from urlparse import urlparse

import bleach
import jinja2

from django.conf import settings
from django.utils import encoding


import amo


def get_outgoing_url(url):
    """
    Bounce a URL off an outgoing URL redirector, such as outgoing.mozilla.org.
    """
    if not settings.REDIRECT_URL:
        return url

    url_netloc = urlparse(url).netloc

    # No double-escaping, and some domain names are excluded.
    if (url_netloc == urlparse(settings.REDIRECT_URL).netloc
        or url_netloc in settings.REDIRECT_URL_WHITELIST):
        return url

    url = encoding.smart_str(jinja2.utils.Markup(url).unescape())
    sig = hmac.new(settings.REDIRECT_SECRET_KEY,
                   msg=url, digestmod=hashlib.sha256).hexdigest()
    # Let '&=' through so query params aren't escaped.  We probably shouldn't
    # bother to quote the query part at all.
    return '/'.join([settings.REDIRECT_URL.rstrip('/'), sig,
                     urllib.quote(url, safe='/&=')])


def linkify_bounce_url_callback(attrs, new=False):
    """Linkify callback that uses get_outgoing_url."""
    attrs['href'] = get_outgoing_url(attrs['href'])
    return attrs


def linkify_with_outgoing(text, nofollow=True):
    """Wrapper around bleach.linkify: uses get_outgoing_url."""
    callbacks = [linkify_bounce_url_callback]
    if nofollow:
        callbacks.append(bleach.callbacks.nofollow)
    return bleach.linkify(unicode(text), callbacks=callbacks)
