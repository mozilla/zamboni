import logging

from post_request_task.task import task

from mkt.feed.models import FeedApp, FeedCollection

log = logging.getLogger('z.feed')


@task
def _migrate_collection_colors(ids, model):
    """Migrate deprecated background color (hex) to color (name)."""
    cls = FeedApp
    if model == 'collection':
        cls = FeedCollection

    for obj in cls.objects.filter(id__in=ids):
        if obj.background_color and not obj.color:
            try:
                color = {
                    '#CE001C': 'ruby',
                    '#F78813': 'amber',
                    '#00953F': 'emerald',
                    '#0099D0': 'aquamarine',
                    '#1E1E9C': 'sapphire',
                    '#5A197E': 'amethyst',
                    '#A20D55': 'garnet'
                }.get(obj.background_color, 'aquamarine')
            except KeyError:
                continue
            obj.update(color=color)
            log.info('Migrated %s:%s from %s to %s' %
                     (model, unicode(obj.id), obj.background_color, color))
