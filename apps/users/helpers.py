import random

from django.utils.encoding import smart_unicode

import jinja2
from jingo import register
from tower import ugettext as _


@register.function
def emaillink(email, title=None, klass=None):
    if not email:
        return ""

    fallback = email[::-1]  # reverse
    # inject junk somewhere
    i = random.randint(0, len(email) - 1)
    fallback = u"%s%s%s" % (jinja2.escape(fallback[:i]),
                            u'<span class="i">null</span>',
                            jinja2.escape(fallback[i:]))
    # replace @ and .
    fallback = fallback.replace('@', '&#x0040;').replace('.', '&#x002E;')

    if title:
        title = jinja2.escape(title)
    else:
        title = '<span class="emaillink">%s</span>' % fallback

    node = (u'<a%s href="#">%s</a><span class="emaillink js-hidden">%s</span>'
            % ((' class="%s"' % klass) if klass else '', title, fallback))
    return jinja2.Markup(node)


def _user_link(user):
    if isinstance(user, basestring):
        return user
    # Marketplace doesn't have user profile pages.
    return jinja2.escape(smart_unicode(user.name))


@register.filter
def user_link(user):
    if not user:
        return ''
    return jinja2.Markup(_user_link(user))


@register.function
def users_list(users, size=None):
    if not users:
        return ''

    tail = []
    if size and size < len(users):
        users = users[:size]
        tail = [_('others', 'user_list_others')]

    return jinja2.Markup(', '.join(map(_user_link, users) + tail))


@register.function
def user_data(amo_user):
    anonymous, currency, pre_auth, email = True, 'USD', False, ''
    if hasattr(amo_user, 'is_anonymous'):
        anonymous = amo_user.is_anonymous()
    if not anonymous:
        email = amo_user.email

    return {'anonymous': anonymous, 'currency': currency, 'email': email}
