from django.conf import settings
from django.core.urlresolvers import reverse

import jinja2
from jingo import register
from tower import ugettext as _

import mkt
from mkt.access import acl
from mkt.constants import CATEGORY_CHOICES_DICT
from mkt.site.helpers import mkt_breadcrumbs, page_title
from mkt.webapps.helpers import new_context


register.function(acl.check_addon_ownership)


@register.inclusion_tag('developers/apps/listing/items.html')
@jinja2.contextfunction
def hub_addon_listing_items(context, addons, src=None, notes=None):
    return new_context(**locals())


@register.function
@jinja2.contextfunction
def hub_page_title(context, title=None, addon=None):
    """Wrapper for developer page titles."""
    if addon:
        title = u'%s | %s' % (title, addon.name)
    else:
        devhub = _('Developers')
        title = '%s | %s' % (title, devhub) if title else devhub
    return page_title(context, title)


@register.function
@jinja2.contextfunction
def hub_breadcrumbs(context, addon=None, items=None, add_default=False):
    """
    Wrapper function for ``breadcrumbs``. Prepends 'Developers' breadcrumb.

    **items**
        list of [(url, label)] to be inserted after Add-on.
    **addon**
        Adds the Add-on name to the end of the trail.  If items are
        specified then the Add-on will be linked.
    **add_default**
        Prepends trail back to home when True.  Default is False.
    """
    crumbs = [(reverse('ecosystem.landing'), _('Developers'))]
    title = _('My Submissions')
    link = reverse('mkt.developers.apps')

    if addon:
        if not addon and not items:
            # We are at the end of the crumb trail.
            crumbs.append((None, title))
        else:
            crumbs.append((link, title))
        if items:
            url = addon.get_dev_url()
        else:
            # The Addon is the end of the trail.
            url = None
        crumbs.append((url, addon.name))
    if items:
        crumbs.extend(items)

    if len(crumbs) == 1:
        crumbs = []

    return mkt_breadcrumbs(context, items=crumbs)


@register.function
def mkt_status_class(addon):
    if addon.disabled_by_user and addon.status != mkt.STATUS_DISABLED:
        cls = 'disabled'
    else:
        cls = mkt.STATUS_CHOICES_API.get(addon.status, 'none')
    return 'status-' + cls


@register.function
def mkt_file_status_class(addon, version):
    if addon.disabled_by_user and addon.status != mkt.STATUS_DISABLED:
        cls = 'disabled'
    else:
        file = version.all_files[0]
        cls = mkt.STATUS_CHOICES_API.get(file.status, 'none')
    return 'status-' + cls


@register.function
def log_action_class(action_id):
    if action_id in mkt.LOG_BY_ID:
        cls = mkt.LOG_BY_ID[action_id].action_class
        if cls is not None:
            return 'action-' + cls


@register.function
def dev_agreement_ok(user):
    latest = settings.DEV_AGREEMENT_LAST_UPDATED
    if not latest:
        # Value not set for last updated.
        return True

    if user.is_anonymous():
        return True

    if not user.read_dev_agreement:
        # If you don't have any apps, we we won't worry about this because
        # you'll be prompted on the first submission.
        return True

    current = user.read_dev_agreement
    if current and current.date() < latest:
        # The dev agreement has been updated since you last submitted.
        return False

    return True


@register.filter
def categories_names(cat_slugs):
    if cat_slugs is None:
        return []
    return sorted(unicode(CATEGORY_CHOICES_DICT.get(k)) for k in cat_slugs)
