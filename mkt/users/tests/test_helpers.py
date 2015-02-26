# -*- coding: utf-8 -*-
import re

from nose.tools import eq_

from mkt.users.helpers import emaillink, user_data
from mkt.users.models import UserProfile


def test_emaillink():
    email = 'me@example.com'
    obfuscated = unicode(emaillink(email))

    # remove junk
    m = re.match(
        r'<a href="#"><span class="emaillink">(.*?)'
        '<span class="i">null</span>(.*)</span></a>'
        '<span class="emaillink js-hidden">(.*?)'
        '<span class="i">null</span>(.*)</span>', obfuscated)
    obfuscated = (''.join((m.group(1), m.group(2)))
                  .replace('&#x0040;', '@').replace('&#x002E;', '.'))[::-1]
    eq_(email, obfuscated)

    title = 'E-mail your question'
    obfuscated = unicode(emaillink(email, title))
    m = re.match(
        r'<a href="#">(.*)</a>'
        '<span class="emaillink js-hidden">(.*?)'
        '<span class="i">null</span>(.*)</span>', obfuscated)
    eq_(title, m.group(1))
    obfuscated = (''.join((m.group(2), m.group(3)))
                  .replace('&#x0040;', '@').replace('&#x002E;', '.'))[::-1]
    eq_(email, obfuscated)


def test_user_data():
    u = user_data(UserProfile(pk=1))
    eq_(u['anonymous'], False)
