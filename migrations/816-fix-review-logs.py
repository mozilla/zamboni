"""
When the Review model moved from apps/reviews/ to mkt/ratings/ the django
app_label changed. We use the app_label + model_name to refer to activity log
relationships, and the move broke points to Reviews.

This migration fixes this.

"""
import amo
from mkt.developers.models import ActivityLog


REVIEW_ACTIONS = [
    amo.LOG.ADD_REVIEW.id,
    amo.LOG.APPROVE_REVIEW.id,
    amo.LOG.DELETE_REVIEW.id,
    amo.LOG.EDIT_REVIEW.id,
]


def run():

    logs = (ActivityLog.objects.filter(action__in=REVIEW_ACTIONS)
            .values('id', '_arguments'))
    for log in logs:
        (ActivityLog.objects.get(pk=log['id'])
         .update(_arguments=log['_arguments'].replace('"reviews.review"',
                                                      '"ratings.review"')))
