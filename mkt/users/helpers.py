import random

import jinja2
from jingo import register


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
def user_data(user):
    anonymous, currency, preauth, email = True, 'USD', False, ''  # noqa
    if hasattr(user, 'is_anonymous'):
        anonymous = user.is_anonymous()
    if not anonymous:
        email = user.email

    return {'anonymous': anonymous, 'currency': currency, 'email': email}
