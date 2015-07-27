#!/usr/bin/env python

from celery import task

from mkt.site.utils import chunked
from mkt.site.decorators import use_master
from mkt.webapps.models import Webapp


@task
@use_master
def reindex_reviews(addon_id, **kw):
    try:
        # Emit post-save signals so ES gets the correct bayesian ratings.
        # One review is enough to fire off the tasks.
        Webapp.objects.get(id=addon_id).reviews[0].save()
    except IndexError:
        # It's possible that `total_reviews` was wrong.
        print 'No reviews found for %s' % addon_id


def run():
    """Fix app ratings in ES (bug 787162)."""
    ids = (Webapp.objects.filter(total_reviews__gt=0)
           .values_list('id', flat=True))
    for chunk in chunked(ids, 50):
        [reindex_reviews.delay(pk) for pk in chunk]
