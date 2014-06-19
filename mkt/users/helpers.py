import random

import jinja2
from jingo import register

from amo import urlresolvers, utils


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


@register.function
def user_data(amo_user):
    anonymous, currency, pre_auth, email = True, 'USD', False, ''
    if hasattr(amo_user, 'is_anonymous'):
        anonymous = amo_user.is_anonymous()
    if not anonymous:
        email = amo_user.email

    return {'anonymous': anonymous, 'currency': currency, 'email': email}


@register.function
@jinja2.contextfunction
def fxa_login_link(context):
    next = context['request'].path

    qs = context['request'].GET.urlencode()

    if qs:
        next += '?' + qs

    l = utils.urlparams(urlresolvers.reverse('fxa_login'), to=next)
    return l
