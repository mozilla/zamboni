from django.core.management.base import BaseCommand

from mkt.feed.models import FeedApp, FeedCollection
from mkt.feed.tasks import _migrate_collection_colors
from mkt.site.utils import chunked


class Command(BaseCommand):
    help = ('Migrate `background_color` (hex) to `color` (color name) since '
            'deserializing background colors by hex is deprecated.')

    def handle(self, *args, **options):
        app_ids = (FeedApp.objects.filter(color__isnull=True)
                                  .values_list('id', flat=True))
        coll_ids = (FeedCollection.objects.filter(color__isnull=True)
                                          .values_list('id', flat=True))

        for chunk in chunked(app_ids, 100):
            _migrate_collection_colors.delay(chunk, 'app')

        for chunk in chunked(coll_ids, 100):
            _migrate_collection_colors.delay(chunk, 'collection')
