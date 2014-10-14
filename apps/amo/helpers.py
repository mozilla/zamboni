import json as jsonlib
from urlparse import urljoin

from django.core.urlresolvers import reverse
from django.template import defaultfilters

import jinja2
import six
from jingo import env, register
# Needed to make sure our own |f filter overrides jingo's one.
from jingo import helpers  # noqa
from tower import ugettext as _

from amo import utils
from mkt.translations.helpers import truncate
from mkt.site.utils import get_outgoing_url


# Yanking filters from Django.
register.filter(defaultfilters.slugify)

# Registering some utils as filters:
urlparams = register.filter(utils.urlparams)
register.filter(utils.epoch)
register.filter(utils.isotime)
register.function(dict)
register.function(utils.randslice)


@register.filter
def impala_paginator(pager):
    t = env.get_template('amo/impala/paginator.html')
    return jinja2.Markup(t.render({'pager': pager}))


@register.function
@jinja2.contextfunction
def login_link(context):
    next = context['request'].path

    qs = context['request'].GET.urlencode()

    if qs:
        next += '?' + qs

    l = urlparams(reverse('users.login'), to=next)
    return l


@register.function
@jinja2.contextfunction
def impala_breadcrumbs(context, items=list(), add_default=True, crumb_size=40):
    """
    show a list of breadcrumbs. If url is None, it won't be a link.
    Accepts: [(url, label)]
    """
    if add_default:
        crumbs = [(reverse('home'), _('Apps Marketplace'))]
    else:
        crumbs = []

    # add user-defined breadcrumbs
    if items:
        try:
            crumbs += items
        except TypeError:
            crumbs.append(items)

    crumbs = [(url, truncate(label, crumb_size)) for (url, label) in crumbs]
    c = {'breadcrumbs': crumbs, 'has_home': add_default}
    t = env.get_template('amo/impala/breadcrumbs.html').render(c)
    return jinja2.Markup(t)


@register.filter
def json(s):
    return jsonlib.dumps(s)


@register.filter
def strip_controls(s):
    """
    Strips control characters from a string.
    """
    # Translation table of control characters.
    control_trans = dict((n, None) for n in xrange(32) if n not in [10, 13])
    rv = unicode(s).translate(control_trans)
    return jinja2.Markup(rv) if isinstance(s, jinja2.Markup) else rv


@register.filter
def external_url(url):
    """Bounce a URL off outgoing.mozilla.org."""
    return get_outgoing_url(unicode(url))


@register.function
@jinja2.contextfunction
def media(context, url, key='MEDIA_URL'):
    """Get a MEDIA_URL link with a cache buster querystring."""
    if 'BUILD_ID' in context:
        build = context['BUILD_ID']
    else:
        if url.endswith('.js'):
            build = context['BUILD_ID_JS']
        elif url.endswith('.css'):
            build = context['BUILD_ID_CSS']
        else:
            build = context['BUILD_ID_IMG']
    return urljoin(context[key], utils.urlparams(url, b=build))


@register.function
@jinja2.contextfunction
def static(context, url):
    """Get a STATIC_URL link with a cache buster querystring."""
    return media(context, url, 'STATIC_URL')


@register.filter
def f(string, *args, **kwargs):
    """This overrides jingo.helpers.f to convert input to unicode if needed.

    This is needed because of
    https://github.com/jbalogh/jingo/pull/54#issuecomment-36728948

    """
    if not isinstance(string, six.text_type):
        string = six.text_type(string)
    return string.format(*args, **kwargs)
