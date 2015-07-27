import json
import logging
import datetime

from celery import task

import mkt
from mkt.constants.regions import REGIONS_CHOICES_SLUG
from mkt.monolith.models import MonolithRecord
from mkt.site.decorators import use_master
from mkt.ratings.models import Review
from mkt.webapps.models import AddonUser, Webapp
from mkt.users.models import UserProfile


log = logging.getLogger('z.stats')


@task
@use_master
def update_monolith_stats(metric, date, **kw):
    log.info('Updating monolith statistics (%s) for (%s)' % (metric, date))

    jobs = _get_monolith_jobs(date)[metric]

    for job in jobs:
        try:
            # Only record if count is greater than zero.
            count = job['count']()
            if count:
                value = {'count': count}
                if 'dimensions' in job:
                    value.update(job['dimensions'])

                MonolithRecord.objects.create(recorded=date, key=metric,
                                              value=json.dumps(value))

                log.info('Monolith stats details: (%s) has (%s) for (%s). '
                         'Value: %s' % (metric, count, date, value))
            else:
                log.info('Monolith stat (%s) did not record due to falsy '
                         'value (%s) for (%s)' % (metric, count, date))

        except Exception as e:
            log.critical('Update of monolith table failed: (%s): %s'
                         % ([metric, date], e))


def _get_monolith_jobs(date=None):
    """
    Return a dict of Monolith based statistics queries.

    The dict is of the form::

        {'<metric_name>': [{'count': <callable>, 'dimensions': <dimensions>}]}

    Where `dimensions` is an optional dict of dimensions we expect to filter on
    via Monolith.

    If a date is specified and applies to the job it will be used.  Otherwise
    the date will default to today().
    """
    if not date:
        date = datetime.date.today()

    # If we have a datetime make it a date so H/M/S isn't used.
    if isinstance(date, datetime.datetime):
        date = date.date()

    next_date = date + datetime.timedelta(days=1)

    stats = {
        # Marketplace reviews.
        'apps_review_count_new': [{
            'count': Review.objects.filter(
                created__range=(date, next_date), editorreview=0).count,
        }],

        # New users
        'mmo_user_count_total': [{
            'count': UserProfile.objects.filter(
                created__lt=next_date,
                source=mkt.LOGIN_SOURCE_MMO_BROWSERID).count,
        }],
        'mmo_user_count_new': [{
            'count': UserProfile.objects.filter(
                created__range=(date, next_date),
                source=mkt.LOGIN_SOURCE_MMO_BROWSERID).count,
        }],

        # New developers.
        'mmo_developer_count_total': [{
            'count': AddonUser.objects.filter(
                user__created__lt=next_date).values('user').distinct().count,
        }],

        # App counts.
        'apps_count_new': [{
            'count': Webapp.objects.filter(
                created__range=(date, next_date)).count,
        }],
    }

    # Add various "Apps Added" for all the dimensions we need.
    apps = Webapp.objects.filter(created__range=(date, next_date))

    package_counts = []
    premium_counts = []

    # privileged==packaged for our consideration.
    package_types = mkt.ADDON_WEBAPP_TYPES.copy()
    package_types.pop(mkt.ADDON_WEBAPP_PRIVILEGED)

    for region_slug, region in REGIONS_CHOICES_SLUG:
        # Apps added by package type and region.
        for package_type in package_types.values():
            package_counts.append({
                'count': (apps
                          .filter(is_packaged=package_type == 'packaged')
                          .exclude(addonexcludedregion__region=region.id)
                          .count),
                'dimensions': {'region': region_slug,
                               'package_type': package_type},
            })

        # Apps added by premium type and region.
        for premium_type, pt_name in mkt.ADDON_PREMIUM_API.items():
            premium_counts.append({
                'count': (apps
                          .filter(premium_type=premium_type)
                          .exclude(addonexcludedregion__region=region.id)
                          .count),
                'dimensions': {'region': region_slug,
                               'premium_type': pt_name},
            })

    stats.update({'apps_added_by_package_type': package_counts})
    stats.update({'apps_added_by_premium_type': premium_counts})

    # Add various "Apps Available" for all the dimensions we need.
    apps = Webapp.objects.filter(_current_version__reviewed__lt=next_date,
                                 status__in=mkt.LISTED_STATUSES,
                                 disabled_by_user=False)
    package_counts = []
    premium_counts = []

    for region_slug, region in REGIONS_CHOICES_SLUG:
        # Apps available by package type and region.
        for package_type in package_types.values():
            package_counts.append({
                'count': (apps
                          .filter(is_packaged=package_type == 'packaged')
                          .exclude(addonexcludedregion__region=region.id)
                          .count),
                'dimensions': {'region': region_slug,
                               'package_type': package_type},
            })

        # Apps available by premium type and region.
        for premium_type, pt_name in mkt.ADDON_PREMIUM_API.items():
            premium_counts.append({
                'count': (apps
                          .filter(premium_type=premium_type)
                          .exclude(addonexcludedregion__region=region.id)
                          .count),
                'dimensions': {'region': region_slug,
                               'premium_type': pt_name},
            })

    stats.update({'apps_available_by_package_type': package_counts})
    stats.update({'apps_available_by_premium_type': premium_counts})

    return stats
