import commonware.log
from celeryutils import task

from .models import UserProfile


task_log = commonware.log.getLogger('z.task')


@task(rate_limit='15/m')
def update_user_ratings_task(data, **kw):
    task_log.info("[%s@%s] Updating add-on author's ratings." %
                   (len(data), update_user_ratings_task.rate_limit))
    for pk, rating in data:
        rating = "%.2f" % round(rating, 2)
        UserProfile.objects.filter(pk=pk).update(averagerating=rating)
