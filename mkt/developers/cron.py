import logging

import cronjobs
from celery.task.sets import TaskSet
from django.utils.translation import ugettext as _

import mkt
from mkt.developers.tasks import region_email, region_exclude
from mkt.reviewers.models import RereviewQueue
from mkt.site.utils import chunked
from mkt.webapps.models import AddonExcludedRegion, Webapp


log = logging.getLogger('z.mkt.developers.cron')


def _region_email(ids, region_ids):
    ts = [region_email.subtask(args=[chunk, region_ids])
          for chunk in chunked(ids, 100)]
    TaskSet(ts).apply_async()


@cronjobs.register
def send_new_region_emails(regions):
    """Email app developers notifying them of new regions added."""
    region_ids = [r.id for r in regions]
    excluded = (AddonExcludedRegion.objects
                .filter(region__in=region_ids)
                .values_list('addon', flat=True))
    ids = (Webapp.objects.exclude(id__in=excluded)
           .filter(enable_new_regions=True)
           .values_list('id', flat=True))
    _region_email(ids, region_ids)


def _region_exclude(ids, region_ids):
    ts = [region_exclude.subtask(args=[chunk, region_ids])
          for chunk in chunked(ids, 100)]
    TaskSet(ts).apply_async()


@cronjobs.register
def exclude_new_region(regions):
    """
    Update blocked regions based on a list of regions to exclude.
    """
    region_ids = [r.id for r in regions]
    excluded = set(AddonExcludedRegion.objects
                   .filter(region__in=region_ids)
                   .values_list('addon', flat=True))
    ids = (Webapp.objects.exclude(id__in=excluded)
           .filter(enable_new_regions=False)
           .values_list('id', flat=True))
    _region_exclude(ids, region_ids)


def _flag_rereview_adult(app, ratings_body, rating):
    """Flag app for rereview if it receives an Adult content rating."""
    old_rating = app.content_ratings.filter(ratings_body=ratings_body.id)
    if not old_rating.exists():
        return

    if rating.adult and not old_rating[0].get_rating().adult:
        RereviewQueue.flag(
            app, mkt.LOG.CONTENT_RATING_TO_ADULT,
            message=_('Content rating changed to Adult.'))
