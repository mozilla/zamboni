import logging
from celeryutils import task
from mpconstants import collection_colors as coll_colors

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
                color = coll_colors.COLLECTION_COLORS_REVERSE[
                    obj.background_color]
            except KeyError:
                continue
            obj.update(color=color)
            log.info('Migrated %s:%s from %s to %s' %
                     (model, unicode(obj.id), obj.background_color, color))
