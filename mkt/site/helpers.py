import json
import uuid

from django.conf import settings

import commonware.log
import jinja2
from jingo import env, register
from jingo_minify import helpers as jingo_minify_helpers
from tower import ugettext as _

from amo.helpers import urlparams
from amo.urlresolvers import reverse

from mkt.translations.helpers import truncate
from mkt.users.views import fxa_oauth_api


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
                  'is_packaged': json.dumps(product.is_packaged)}

    installed = None

    if request.amo_user:
        installed_set = request.amo_user.installed_set
        installed = installed_set.filter(addon=product).exists()

    # Handle premium apps.
    if product.has_premium():
        # User has purchased app.
        purchased = (request.amo_user and
                     product.pk in request.amo_user.purchase_ids())

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
        'recordUrl': urlparams(receipt_url, src=src),
        'tokenUrl': token_url,
        'is_packaged': product.is_packaged,
        'src': src
    }

    if product.premium:
        ret.update({
            'price': product.get_price(region=request.REGION.id),
            'priceLocale': product.get_price_locale(region=request.REGION.id),
        })

        if request.amo_user:
            ret['isPurchased'] = purchased

    # Jinja2 escape everything except this whitelist so that bool is retained
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
        'addons': [
            ('Fake mail', reverse('zadmin.mail')),
        ],
        'users': [
            ('Configure groups', reverse('admin:access_group_changelist')),
        ],
        'settings': [
            ('View site settings', reverse('zadmin.settings')),
            ('Django admin pages', reverse('zadmin.home')),
        ],
        'tools': [
            ('View request environment', reverse('amo.env')),
            ('View elasticsearch settings', reverse('zadmin.elastic')),
            ('Purge data from memcache', reverse('zadmin.memcache')),
            ('Generate error', reverse('zadmin.generate-error')),
            ('Site Status', reverse('amo.monitor')),
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


@jinja2.contextfunction
@register.function
def fxa_auth_info(context=None):
    state = uuid.uuid4().hex
    return (state,
            urlparams(
                fxa_oauth_api('authorization'),
                client_id=settings.FXA_CLIENT_ID,
                state=state,
                scope='profile'))
