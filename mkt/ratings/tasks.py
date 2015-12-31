import logging

from django.db.models import Count, Avg, F

from celery import task

from lib.post_request_task.task import task as post_request_task
from mkt.webapps.models import Webapp

from .models import Review


log = logging.getLogger('z.task')


@task(rate_limit='50/m')
def update_denorm(*pairs, **kw):
    """
    Takes a bunch of (addon, user) pairs and sets the denormalized fields for
    all reviews matching that pair.
    """
    log.info('[%s@%s] Updating review denorms.' %
             (len(pairs), update_denorm.rate_limit))
    using = kw.get('using')
    for addon, user in pairs:
        reviews = list(Review.objects.valid().using(using)
                       .filter(addon=addon, user=user).order_by('created'))
        if not reviews:
            continue

        for idx, review in enumerate(reviews):
            review.previous_count = idx
            review.is_latest = False
        reviews[-1].is_latest = True

        for review in reviews:
            review.save()


@post_request_task
def addon_review_aggregates(*addons, **kw):
    log.info('[%s@%s] Updating total reviews and average ratings.' %
             (len(addons), addon_review_aggregates.rate_limit))
    using = kw.get('using')
    addon_objs = list(Webapp.objects.filter(pk__in=addons))
    stats = dict((x[0], x[1:]) for x in
                 Review.objects.valid().using(using)
                 .filter(addon__in=addons, is_latest=True)
                 .values_list('addon')
                 .annotate(Avg('rating'), Count('addon')).order_by())
    for addon in addon_objs:
        rating, reviews = stats.get(addon.id, [0, 0])
        addon.update(total_reviews=reviews, average_rating=rating)

    # Delay bayesian calculations to avoid slave lag.
    addon_bayesian_rating.apply_async(args=addons, countdown=5)


@task
def addon_bayesian_rating(*addons, **kw):
    log.info('[%s@%s] Updating bayesian ratings.' %
             (len(addons), addon_bayesian_rating.rate_limit))

    avg = Webapp.objects.aggregate(rating=Avg('average_rating'),
                                   reviews=Avg('total_reviews'))
    # Rating can be NULL in the DB, so don't update it if it's not there.
    if avg['rating'] is None:
        return
    mc = avg['reviews'] * avg['rating']
    for addon in Webapp.objects.filter(id__in=addons):
        if addon.average_rating is None:
            # Ignoring addons with no average rating.
            continue

        q = Webapp.objects.filter(id=addon.id)
        if addon.total_reviews:
            num = mc + F('total_reviews') * F('average_rating')
            denom = avg['reviews'] + F('total_reviews')
            q.update(bayesian_rating=num / denom)
        else:
            q.update(bayesian_rating=0)
