import json as jsonlib
import random
import re
from urlparse import urljoin

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.forms import CheckboxInput
from django.template import defaultfilters
from django.utils import translation
from django.utils.encoding import smart_unicode

import jinja2
import six
from babel.support import Format
from jingo import env, register
# Needed to make sure our own |f filter overrides jingo's one.
from jingo import helpers  # noqa
from tower import ugettext as _, strip_whitespace

import amo
from amo import urlresolvers, utils
from constants.licenses import PERSONA_LICENSES_IDS
from mkt.translations.helpers import truncate
from mkt.versions.models import License


# Yanking filters from Django.
register.filter(defaultfilters.slugify)

# Registering some utils as filters:
urlparams = register.filter(utils.urlparams)
register.filter(utils.epoch)
register.filter(utils.isotime)
register.function(dict)
register.function(utils.randslice)


@register.filter
def link(item):
    html = """<a href="%s">%s</a>""" % (item.get_url_path(),
                                        jinja2.escape(item.name))
    return jinja2.Markup(html)


@register.filter
def xssafe(value):
    """
    Like |safe but for strings with interpolation.

    By using |xssafe you assert that you have written tests proving an
    XSS can't happen here.
    """
    return jinja2.Markup(value)


@register.filter
def babel_datetime(dt, format='medium'):
    return _get_format().datetime(dt, format=format) if dt else ''


@register.filter
def babel_date(date, format='medium'):
    return _get_format().date(date, format=format) if date else ''


@register.function
def locale_url(url):
    """Marketplace doesn't use locale prefixed URLs but we call this a lot."""
    # TODO: Remove uses of this in templates.
    return url


@register.inclusion_tag('includes/refinements.html')
@jinja2.contextfunction
def refinements(context, items, title, thing):
    d = dict(context.items())
    d.update(items=items, title=title, thing=thing)
    return d


@register.function
def url(viewname, *args, **kwargs):
    """Helper for Django's ``reverse`` in templates."""
    add_prefix = kwargs.pop('add_prefix', True)
    host = kwargs.pop('host', '')
    src = kwargs.pop('src', '')
    url = '%s%s' % (host, urlresolvers.reverse(viewname,
                                               args=args,
                                               kwargs=kwargs,
                                               add_prefix=add_prefix))
    if src:
        url = urlparams(url, src=src)
    return url


@register.filter
def paginator(pager):
    return Paginator(pager).render()


@register.filter
def impala_paginator(pager):
    t = env.get_template('amo/impala/paginator.html')
    return jinja2.Markup(t.render({'pager': pager}))


class Paginator(object):

    def __init__(self, pager):
        self.pager = pager

        self.max = 10
        self.span = (self.max - 1) / 2

        self.page = pager.number
        self.num_pages = pager.paginator.num_pages
        self.count = pager.paginator.count

        pager.page_range = self.range()
        pager.dotted_upper = self.num_pages not in pager.page_range
        pager.dotted_lower = 1 not in pager.page_range

    def range(self):
        """Return a list of page numbers to show in the paginator."""
        page, total, span = self.page, self.num_pages, self.span
        if total < self.max:
            lower, upper = 0, total
        elif page < span + 1:
            lower, upper = 0, span * 2
        elif page > total - span:
            lower, upper = total - span * 2, total
        else:
            lower, upper = page - span, page + span - 1
        return range(max(lower + 1, 1), min(total, upper) + 1)

    def render(self):
        c = {'pager': self.pager, 'num_pages': self.num_pages,
             'count': self.count}
        t = env.get_template('amo/paginator.html').render(c)
        return jinja2.Markup(t)


def _get_format():
    lang = translation.get_language()
    return Format(utils.get_locale_from_lang(lang))


@register.filter
def numberfmt(num, format=None):
    return _get_format().decimal(num, format)


@register.filter
def currencyfmt(num, currency):
    if num is None:
        return ''
    return _get_format().currency(num, currency)


def page_name(app=None):
    """Determine the correct page name for the given app (or no app)."""
    if app:
        return _(u'Add-ons for {0}').format(app.pretty)
    else:
        return _('Add-ons')


@register.function
@jinja2.contextfunction
def login_link(context):
    next = context['request'].path

    qs = context['request'].GET.urlencode()

    if qs:
        next += '?' + qs

    l = urlparams(urlresolvers.reverse('users.login'), to=next)
    return l


@register.function
@jinja2.contextfunction
def page_title(context, title, force_webapps=False):
    title = smart_unicode(title)
    base_title = _('Firefox Marketplace')
    return u'%s :: %s' % (title, base_title)


@register.function
@jinja2.contextfunction
def impala_breadcrumbs(context, items=list(), add_default=True, crumb_size=40):
    """
    show a list of breadcrumbs. If url is None, it won't be a link.
    Accepts: [(url, label)]
    """
    if add_default:
        crumbs = [(urlresolvers.reverse('home'), _('Apps Marketplace'))]
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
def absolutify(url, site=None):
    """Takes a URL and prepends the SITE_URL"""
    if url.startswith('http'):
        return url
    else:
        return urljoin(site or settings.SITE_URL, url)


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
def strip_html(s, just_kidding=False):
    """Strips HTML.  Confirm lets us opt out easily."""
    if just_kidding:
        return s

    if not s:
        return ''
    else:
        s = re.sub(r'&lt;.*?&gt;', '', smart_unicode(s, errors='ignore'))
        return re.sub(r'<.*?>', '', s)


@register.filter
def external_url(url):
    """Bounce a URL off outgoing.mozilla.org."""
    return urlresolvers.get_outgoing_url(unicode(url))


@register.filter
def shuffle(sequence):
    """Shuffle a sequence."""
    random.shuffle(sequence)
    return sequence


@register.function
def license_link(license):
    """Link to a code license, including icon where applicable."""
    # If passed in an integer, try to look up the License.
    if isinstance(license, (long, int)):
        if license in PERSONA_LICENSES_IDS:
            # Grab built-in license.
            license = PERSONA_LICENSES_IDS[license]
        else:
            # Grab custom license.
            license = License.objects.filter(id=license)
            if not license.exists():
                return ''
            license = license[0]
    elif not license:
        return ''

    if not getattr(license, 'builtin', True):
        return _('Custom License')

    t = env.get_template('amo/license_link.html').render({'license': license})
    return jinja2.Markup(t)


@register.function
def field(field, label=None, **attrs):
    if label is not None:
        field.label = label
    # HTML from Django is already escaped.
    return jinja2.Markup(u'%s<p>%s%s</p>' %
                         (field.errors, field.label_tag(),
                          field.as_widget(attrs=attrs)))


@register.inclusion_tag('amo/category-arrow.html')
@jinja2.contextfunction
def category_arrow(context, key, prefix):
    d = dict(context.items())
    d.update(key=key, prefix=prefix)
    return d


@register.filter
def timesince(time):
    if not time:
        return u''
    ago = defaultfilters.timesince(time)
    # L10n: relative time in the past, like '4 days ago'
    return _(u'{0} ago').format(ago)


@register.inclusion_tag('amo/recaptcha.html')
@jinja2.contextfunction
def recaptcha(context, form):
    d = dict(context.items())
    d.update(form=form)
    return d


@register.filter
def is_choice_field(value):
    try:
        return isinstance(value.field.widget, CheckboxInput)
    except AttributeError:
        pass


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


@register.function
@jinja2.evalcontextfunction
def attrs(ctx, *args, **kw):
    return jinja2.filters.do_xmlattr(ctx, dict(*args, **kw))


@register.filter
def premium_text(type):
    return amo.ADDON_PREMIUM_TYPES[type]


@register.function
def loc(s):
    """A noop function for strings that are not ready to be localized."""
    return strip_whitespace(s)


@register.function
@jinja2.contextfunction
def hasOneToOne(context, obj, attr):
    try:
        getattr(obj, attr)
        return True
    except ObjectDoesNotExist:
        return False


@register.function
def no_results_amo():
    # This prints a "No results found" message. That's all. Carry on.
    t = env.get_template('amo/no_results.html').render()
    return jinja2.Markup(t)


@register.filter
def f(string, *args, **kwargs):
    """This overrides jingo.helpers.f to convert input to unicode if needed.

    This is needed because of
    https://github.com/jbalogh/jingo/pull/54#issuecomment-36728948

    """
    if not isinstance(string, six.text_type):
        string = six.text_type(string)
    return string.format(*args, **kwargs)
