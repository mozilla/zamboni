import json as jsonlib
import pytz
from urlparse import urljoin

from django.conf import settings
from django.core.urlresolvers import reverse
from django.forms import CheckboxInput
from django.template import defaultfilters
from django.utils import translation
from django.utils.encoding import smart_unicode

import commonware.log
import jinja2
from babel.support import Format
from jingo import env, register
# Needed to make sure our own |f filter overrides jingo's one.
from jingo import helpers  # noqa
from jingo_minify import helpers as jingo_minify_helpers
from six import text_type
from tower import ugettext as _

from mkt.translations.helpers import truncate
from mkt.translations.utils import get_locale_from_lang
from mkt.site.utils import append_tz


log = commonware.log.getLogger('z.mkt.site')


@jinja2.contextfunction
@register.function
def css(context, bundle, media=False, debug=None):
    if debug is None:
        debug = settings.TEMPLATE_DEBUG

    # ?debug=true gives you unminified CSS for testing on -dev/prod.
    if context['request'].GET.get('debug'):
        debug = True

    return jingo_minify_helpers.css(bundle, media, debug)


@jinja2.contextfunction
@register.function
def js(context, bundle, debug=None, defer=False, async=False):
    if debug is None:
        debug = settings.TEMPLATE_DEBUG

    # ?debug=true gives you unminified JS for testing on -dev/prod.
    if context['request'].GET.get('debug'):
        debug = True

    return jingo_minify_helpers.js(bundle, debug, defer, async)


@register.function
def no_results():
    # This prints a "No results found" message. That's all. Carry on.
    t = env.get_template('site/helpers/no_results.html').render()
    return jinja2.Markup(t)


@jinja2.contextfunction
@register.function
def market_button(context, product, receipt_type=None, classes=None):
    request = context['request']
    purchased = False
    classes = (classes or []) + ['button', 'product']
    reviewer = receipt_type == 'reviewer'
    data_attrs = {'manifest_url': product.get_manifest_url(reviewer),
                  'is_packaged': jsonlib.dumps(product.is_packaged)}

    installed = None

    if request.user.is_authenticated():
        installed_set = request.user.installed_set
        installed = installed_set.filter(webapp=product).exists()

    # Handle premium apps.
    if product.has_premium():
        # User has purchased app.
        purchased = (request.user.is_authenticated() and
                     product.pk in request.user.purchase_ids())

        # App authors are able to install their apps free of charge.
        if (not purchased and
                request.check_ownership(product, require_author=True)):
            purchased = True

    if installed or purchased or not product.has_premium():
        label = _('Install')
    else:
        label = product.get_tier_name()

    # Free apps and purchased apps get active install buttons.
    if not product.is_premium() or purchased:
        classes.append('install')

    c = dict(product=product, label=label, purchased=purchased,
             data_attrs=data_attrs, classes=' '.join(classes))
    t = env.get_template('site/helpers/webapp_button.html')
    return jinja2.Markup(t.render(c))


def product_as_dict(request, product, purchased=None, receipt_type=None,
                    src=''):
    receipt_url = (reverse('receipt.issue', args=[product.app_slug]) if
                   receipt_type else product.get_detail_url('record'))
    token_url = reverse('generate-reviewer-token', args=[product.app_slug])

    src = src or request.GET.get('src', '')
    reviewer = receipt_type == 'reviewer'

    # This is the only info. we need to render the app buttons on the
    # Reviewer Tools pages.
    ret = {
        'id': product.id,
        'name': product.name,
        'categories': product.categories,
        'manifest_url': product.get_manifest_url(reviewer),
        'recordUrl': helpers.urlparams(receipt_url, src=src),
        'tokenUrl': token_url,
        'is_packaged': product.is_packaged,
        'src': src
    }

    if product.premium:
        ret.update({
            'price': product.get_price(region=request.REGION.id),
            'priceLocale': product.get_price_locale(region=request.REGION.id),
        })

        if request.user.is_authenticated():
            ret['isPurchased'] = purchased

    # Jinja2 escape everything except this list so that bool is retained
    # for the JSON encoding.
    wl = ('categories', 'currencies', 'isPurchased', 'is_packaged', 'previews',
          'price', 'priceLocale')
    return dict([k, jinja2.escape(v) if k not in wl else v]
                for k, v in ret.items())


@register.function
@jinja2.contextfunction
def mkt_breadcrumbs(context, product=None, items=None, crumb_size=40,
                    add_default=True, cls=None):
    """
    Wrapper function for ``breadcrumbs``.

    **items**
        list of [(url, label)] to be inserted after Add-on.
    **product**
        Adds the App/Add-on name to the end of the trail.  If items are
        specified then the App/Add-on will be linked.
    **add_default**
        Prepends trail back to home when True.  Default is True.
    """
    if add_default:
        crumbs = [(reverse('home'), _('Home'))]
    else:
        crumbs = []

    if product:
        if items:
            url_ = product.get_detail_url()
        else:
            # The Product is the end of the trail.
            url_ = None
        crumbs += [(None, _('Apps')), (url_, product.name)]
    if items:
        crumbs.extend(items)

    if len(crumbs) == 1:
        crumbs = []

    crumbs = [(u, truncate(label, crumb_size)) for (u, label) in crumbs]
    t = env.get_template('site/helpers/breadcrumbs.html').render(
        {'breadcrumbs': crumbs, 'cls': cls})
    return jinja2.Markup(t)


@register.function
def form_field(field, label=None, tag='div', req=None, opt=False, hint=False,
               tooltip=False, some_html=False, cc_startswith=None, cc_for=None,
               cc_maxlength=None, grid=False, cls=None, validate=False):
    attrs = {}
    # Add a `required` attribute so we can do form validation.
    # TODO(cvan): Write tests for kumar some day.
    if validate and field.field.required:
        attrs['required'] = ''
    c = dict(field=field, label=label or field.label, tag=tag, req=req,
             opt=opt, hint=hint, tooltip=tooltip, some_html=some_html,
             cc_startswith=cc_startswith, cc_for=cc_for,
             cc_maxlength=cc_maxlength, grid=grid, cls=cls, attrs=attrs)
    t = env.get_template('site/helpers/simple_field.html').render(c)
    return jinja2.Markup(t)


@register.filter
@jinja2.contextfilter
def timelabel(context, time):
    t = env.get_template('site/helpers/timelabel.html').render({'time': time})
    return jinja2.Markup(t)


@register.function
def mkt_admin_site_links():
    return {
        'webapps': [
            ('Fake mail', reverse('zadmin.mail')),
        ],
        'settings': [
            ('View site settings', reverse('zadmin.settings')),
            ('Django admin pages', reverse('zadmin.home')),
        ],
        'tools': [
            ('View request environment', reverse('mkt.env')),
            ('View elasticsearch settings', reverse('zadmin.elastic')),
            ('Purge data from memcache', reverse('zadmin.memcache')),
            ('Generate error', reverse('zadmin.generate-error')),
            ('Site Status', reverse('mkt.monitor')),
            ('Force Manifest Re-validation',
             reverse('zadmin.manifest_revalidation'))
        ],
    }


@register.function
@jinja2.contextfunction
def get_doc_template(context, template):
    lang = getattr(context['request'], 'LANG', 'en-US')
    if lang in settings.AMO_LANGUAGES:
        try:
            template = env.get_template('%s/%s.html' % (template, lang))
        except jinja2.TemplateNotFound:
            pass
        else:
            return jinja2.Markup(template.render())
    template = env.get_template('%s/en-US.html' % template)
    return jinja2.Markup(template.render())


@register.function
@jinja2.contextfunction
def get_doc_path(context, path, extension):
    """
    Gets the path to a localizable document in the current language with
    fallback to en-US.
    """
    lang = getattr(context['request'], 'LANG', 'en-US')
    if lang in settings.AMO_LANGUAGES:
        try:
            localized_file_path = '%s/%s.%s' % (path, lang, extension)
            with open(localized_file_path):
                return localized_file_path
        except IOError:
            return '%s/en-US.%s' % (path, extension)


@register.filter
def absolutify(url, site=None):
    """Takes a URL and prepends the SITE_URL"""
    if url.startswith('http'):
        return url
    else:
        return urljoin(site or settings.SITE_URL, url)


def _get_format():
    lang = translation.get_language()
    return Format(get_locale_from_lang(lang))


@register.filter
def babel_datetime(dt, format='medium'):
    return _get_format().datetime(dt, format=format) if dt else ''


@register.filter
def babel_date(date, format='medium'):
    return _get_format().date(date, format=format) if date else ''


@register.filter
def is_choice_field(value):
    try:
        return isinstance(value.field.widget, CheckboxInput)
    except AttributeError:
        pass


@register.filter
def numberfmt(num, format=None):
    return _get_format().decimal(num, format)


@register.function
@jinja2.contextfunction
def page_title(context, title):
    title = smart_unicode(title)
    base_title = _('Firefox Marketplace')
    return u'%s | %s' % (title, base_title)


@register.filter
def timesince(time):
    if not time:
        return u''
    ago = defaultfilters.timesince(time)
    # L10n: relative time in the past, like '4 days ago'
    return _(u'{0} ago').format(ago)


@register.function
def url(viewname, *args, **kwargs):
    """Helper for Django's ``reverse`` in templates."""
    host = kwargs.pop('host', '')
    src = kwargs.pop('src', '')
    url = '%s%s' % (host, reverse(viewname, args=args, kwargs=kwargs))
    if src:
        url = helpers.urlparams(url, src=src)
    return url


@register.filter
def impala_paginator(pager):
    t = env.get_template('site/impala_paginator.html')
    return jinja2.Markup(t.render({'pager': pager}))


@register.filter
def json(s):
    return jsonlib.dumps(s)


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
    return urljoin(context[key], helpers.urlparams(url, b=build))


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
    if not isinstance(string, text_type):
        string = text_type(string)
    return string.format(*args, **kwargs)


def strip_controls(s):
    """
    Strips control characters from a string.
    """
    # Translation table of control characters.
    control_trans = dict((n, None) for n in xrange(32) if n not in [10, 13])
    rv = unicode(s).translate(control_trans)
    return jinja2.Markup(rv) if isinstance(s, jinja2.Markup) else rv


@register.function
@jinja2.contextfunction
def prefer_signin(context):
    return 'has_logged_in' in context['request'].COOKIES


@register.filter
def isotime(t):
    """Date/Time format according to ISO 8601"""
    if not hasattr(t, 'tzinfo'):
        return
    return append_tz(t).astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
