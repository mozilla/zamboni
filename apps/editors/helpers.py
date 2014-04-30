import datetime
import math

from django.db import connection

import jinja2
from django.conf import settings
from jingo import register
from tower import ugettext as _

import amo
from addons.helpers import new_context
from editors.models import EscalationQueue, ReviewerScore
from versions.models import Version


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


@register.inclusion_tag('editors/includes/reviewers_score_bar.html')
@jinja2.contextfunction
def reviewers_score_bar(context, types=None, addon_type=None):
    user = context.get('amo_user')

    return new_context(dict(
        request=context.get('request'),
        amo=amo, settings=settings,
        points=ReviewerScore.get_recent(user, addon_type=addon_type),
        total=ReviewerScore.get_total(user),
        **ReviewerScore.get_leaderboards(user, types=types,
                                         addon_type=addon_type)))


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
    id_ = addon.id
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
