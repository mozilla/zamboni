from optparse import make_option

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from celery import chord, group

import mkt
from mkt.site.utils import chunked
from mkt.webapps.models import Webapp
from mkt.webapps.tasks import update_manifests, update_supported_locales


tasks = {
    'update_manifests': {'method': update_manifests,
                         'qs': [Q(is_packaged=False,
                                  status__in=[mkt.STATUS_PENDING,
                                              mkt.STATUS_PUBLIC,
                                              mkt.STATUS_APPROVED],
                                  disabled_by_user=False)]},
    'update_supported_locales': {
        'method': update_supported_locales,
        'qs': [Q(disabled_by_user=False,
                 status__in=[mkt.STATUS_PENDING, mkt.STATUS_PUBLIC,
                             mkt.STATUS_APPROVED])]},
}


class Command(BaseCommand):
    """
    A generic command to run a task on addons.
    Add tasks to the tasks dictionary, providing a list of Q objects if you'd
    like to filter the list down.

    method: the method to delay
    pre: a method to further pre process the pks, must return the pks (opt.)
    qs: a list of Q objects to apply to the method
    kwargs: any extra kwargs you want to apply to the delay method (optional)
    """
    option_list = BaseCommand.option_list + (
        make_option('--task', action='store', type='string',
                    dest='task', help='Run task on the addons.'),
    )

    def handle(self, *args, **options):
        task = tasks.get(options.get('task'))
        if not task:
            raise CommandError('Unknown task provided. Options are: %s'
                               % ', '.join(tasks.keys()))
        qs = Webapp.objects.all()
        if 'qs' in task:
            qs = qs.filter(*task['qs'])
        pks = qs.values_list('pk', flat=True).order_by('-last_updated')
        if 'pre' in task:
            # This is run in process to ensure its run before the tasks.
            pks = task['pre'](pks)
        if pks:
            kw = task.get('kwargs', {})
            # All the remaining tasks go in one group.
            grouping = []
            for chunk in chunked(pks, 100):
                grouping.append(
                    task['method'].subtask(args=[chunk], kwargs=kw))

            # Add the post task on to the end.
            post = None
            if 'post' in task:
                post = task['post'].subtask(args=[], kwargs=kw, immutable=True)
                ts = chord(grouping, post)
            else:
                ts = group(grouping)
            ts.apply_async()
