import datetime

from celery.task.sets import TaskSet
import cronjobs

from mkt.stats import tasks


@cronjobs.register
def update_monolith_stats(date=None):
    """Update monolith statistics."""
    if date:
        date = datetime.datetime.strptime(date, '%Y-%m-%d').date()
    today = date or datetime.date.today()
    jobs = [{'metric': metric,
             'date': today} for metric in tasks._get_monolith_jobs(date)]

    ts = [tasks.update_monolith_stats.subtask(kwargs=kw) for kw in jobs]
    TaskSet(ts).apply_async()
