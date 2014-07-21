import datetime
import math
import urlparse

from django.conf import settings
from django.core.urlresolvers import reverse
from django.db import connection
from django.utils.encoding import smart_str

import jinja2
from jingo import env, register
from tower import ugettext as _
from tower import ugettext_lazy as _lazy

import amo
import mkt
from amo.helpers import impala_breadcrumbs
from mkt.access import acl
from mkt.developers.helpers import mkt_page_title
from mkt.reviewers.models import EscalationQueue, ReviewerScore
from mkt.reviewers.utils import (AppsReviewing, clean_sort_param,
                                 create_sort_link, device_queue_search)
from mkt.versions.models import Version
from mkt.webapps.helpers import new_context


@register.function
@jinja2.contextfunction
def reviewers_breadcrumbs(context, queue=None, items=None):
    """
    Wrapper function for ``breadcrumbs``. Prepends 'Editor Tools'
    breadcrumbs.

    **queue**
        Explicit queue type to set.
    **items**
        list of [(url, label)] to be inserted after Add-on.
    """
    crumbs = [(reverse('reviewers.home'), _('Reviewer Tools'))]

    if queue:
        queues = {'pending': _('Apps'),
                  'rereview': _('Re-reviews'),
                  'updates': _('Updates'),
                  'escalated': _('Escalations'),
                  'device': _('Device'),
                  'moderated': _('Moderated Reviews'),
                  'reviewing': _('Reviewing'),

                  'region': _('Regional Queues')}

        if items:
            url = reverse('reviewers.apps.queue_%s' % queue)
        else:
            # The Addon is the end of the trail.
            url = None
        crumbs.append((url, queues[queue]))

    if items:
        crumbs.extend(items)
    return impala_breadcrumbs(context, crumbs, add_default=True)


@register.function
@jinja2.contextfunction
def reviewers_page_title(context, title=None, addon=None):
    if addon:
        title = u'%s | %s' % (title, addon.name)
    else:
        section = _lazy('Reviewer Tools')
        title = u'%s | %s' % (title, section) if title else section
    return mkt_page_title(context, title)


@register.function
@jinja2.contextfunction
def queue_tabnav(context):
    """
    Returns tuple of tab navigation for the queue pages.

    Each tuple contains three elements: (url, tab_code, tab_text)

    """
    request = context['request']
    counts = context['queue_counts']
    apps_reviewing = AppsReviewing(request).get_apps()

    # Apps.
    if acl.action_allowed(request, 'Apps', 'Review'):
        rv = [
            (reverse('reviewers.apps.queue_pending'), 'pending',
             _('Apps ({0})', counts['pending']).format(counts['pending'])),

            (reverse('reviewers.apps.queue_rereview'), 'rereview',
             _('Re-reviews ({0})', counts['rereview']).format(
             counts['rereview'])),

            (reverse('reviewers.apps.queue_updates'), 'updates',
             _('Updates ({0})', counts['updates']).format(counts['updates'])),
        ]
        if acl.action_allowed(request, 'Apps', 'ReviewEscalated'):
            rv.append((reverse('reviewers.apps.queue_escalated'), 'escalated',
                       _('Escalations ({0})', counts['escalated']).format(
                       counts['escalated'])))
        rv.extend([
            (reverse('reviewers.apps.queue_moderated'), 'moderated',
             _('Moderated Reviews ({0})', counts['moderated'])
             .format(counts['moderated'])),

            (reverse('reviewers.apps.apps_reviewing'), 'reviewing',
             _('Reviewing ({0})').format(len(apps_reviewing))),
        ])
        if acl.action_allowed(request, 'Apps', 'ReviewRegionCN'):
            url_ = reverse('reviewers.apps.queue_region',
                           args=[mkt.regions.CN.slug])
            rv.append((url_, 'region',
                      _('China ({0})').format(counts['region_cn'])))
    else:
        rv = []

    if 'pro' in request.GET:
        device_srch = device_queue_search(request)
        rv.append((reverse('reviewers.apps.queue_device'), 'device',
                  _('Device ({0})').format(device_srch.count()),))

    return rv


@register.function
@jinja2.contextfunction
def logs_tabnav(context):
    """
    Returns tuple of tab navigation for the log pages.

    Each tuple contains three elements: (named url, tab_code, tab_text)
    """
    rv = [
        ('reviewers.apps.logs', 'apps', _('Reviews'))
    ]
    return rv


@register.function
@jinja2.contextfunction
def sort_link(context, pretty_name, sort_field):
    """Get table header sort links.

    pretty_name -- name displayed on table header
    sort_field -- name of get parameter, referenced to in views
    """
    request = context['request']
    sort, order = clean_sort_param(request)

    # Copy search/filter GET parameters.
    get_params = [(k, v) for k, v in
                  urlparse.parse_qsl(smart_str(request.META['QUERY_STRING']))
                  if k not in ('sort', 'order')]

    return create_sort_link(pretty_name, sort_field, get_params,
                            sort, order)


@register.function
def file_compare(file_obj, version):
    return version.files.all()[0]


@register.function
def file_review_status(addon, file):
    if file.status in [amo.STATUS_DISABLED, amo.STATUS_REJECTED]:
        if file.reviewed is not None:
            return _(u'Rejected')
        # Can't assume that if the reviewed date is missing its
        # unreviewed.  Especially for versions.
        else:
            return _(u'Rejected or Unreviewed')
    return amo.STATUS_CHOICES[file.status]


@register.function
def version_status(addon, version):
    return ','.join(unicode(s) for s in version.status)


@register.inclusion_tag('reviewers/includes/reviewers_score_bar.html')
@jinja2.contextfunction
def reviewers_score_bar(context, types=None, addon_type=None):
    user = context.get('user')

    return new_context(dict(
        request=context.get('request'),
        amo=amo, settings=settings,
        points=ReviewerScore.get_recent(user, addon_type=addon_type),
        total=ReviewerScore.get_total(user),
        **ReviewerScore.get_leaderboards(user, types=types,
                                         addon_type=addon_type)))


@register.filter
def mobile_reviewers_paginator(pager):
    # Paginator for non-responsive version of Reviewer Tools.
    t = env.get_template('reviewers/includes/reviewers_paginator.html')
    return jinja2.Markup(t.render({'pager': pager}))


def get_avg_app_waiting_time():
    """
    Returns the rolling average from the past 30 days of the time taken for a
    pending app to become public.
    """
    cursor = connection.cursor()
    cursor.execute('''
        SELECT AVG(DATEDIFF(reviewed, nomination)) FROM versions
        RIGHT JOIN addons ON versions.addon_id = addons.id
        WHERE addontype_id = %s AND status = %s AND
              reviewed >= DATE_SUB(NOW(), INTERVAL 30 DAY)
    ''', (amo.ADDON_WEBAPP, amo.STATUS_PUBLIC))
    row = cursor.fetchone()
    days = 0
    if row:
        try:
            days = math.ceil(float(row[0]))
        except TypeError:
            pass
    return days


@register.function
def get_position(addon):
    excluded_ids = EscalationQueue.objects.values_list('addon', flat=True)
    # Look at all regular versions of webapps which have pending files.
    # This includes both new apps and updates to existing apps, to combine
    # both the regular and updates queue in one big list (In theory, it
    # should take the same time for reviewers to process an app in either
    # queue). Escalated apps are excluded just like in reviewer tools.
    qs = (Version.objects.filter(addon__type=amo.ADDON_WEBAPP,
                                 addon__disabled_by_user=False,
                                 files__status=amo.STATUS_PENDING,
                                 deleted=False)
          .exclude(addon__status__in=(amo.STATUS_DISABLED,
                                      amo.STATUS_DELETED, amo.STATUS_NULL))
          .exclude(addon__id__in=excluded_ids)
          .order_by('nomination', 'created').select_related('addon')
          .no_transforms().values_list('addon_id', 'nomination'))
    position = 0
    nomination_date = None
    for idx, (addon_id, nomination) in enumerate(qs, start=1):
        if addon_id == addon.id:
            position = idx
            nomination_date = nomination
            break
    total = qs.count()
    days = 1
    days_in_queue = 0
    if nomination_date:
        # Estimated waiting time is calculated from the rolling average of
        # the queue waiting time in the past 30 days but subtracting from
        # it the number of days this app has already spent in the queue.
        days_in_queue = (datetime.datetime.now() - nomination_date).days
        days = max(get_avg_app_waiting_time() - days_in_queue, days)
    return {'days': int(days), 'days_in_queue': int(days_in_queue),
            'pos': position, 'total': total}
