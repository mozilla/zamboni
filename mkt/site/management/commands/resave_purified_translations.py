from django.core.management.base import BaseCommand

from mkt.feed.models import (FeedApp, FeedCollection, FeedCollectionMembership,
                             FeedShelf, FeedShelfMembership)
from mkt.versions.models import Version
from mkt.webapps.models import Webapp
from mkt.site.tasks import update_translations
from mkt.site.utils import chunked


class Command(BaseCommand):
    help = "Re-save PurifiedTranslation fields to remove outgoing URLs."

    def handle(self, *args, **kwargs):

        ids = []

        ids.extend(
            FeedCollectionMembership.objects.values_list('group', flat=True))
        ids.extend(
            FeedCollection.objects.values_list('name', flat=True))
        ids.extend(
            FeedCollection.objects.values_list('description', flat=True))
        ids.extend(
            FeedShelfMembership.objects.values_list('group', flat=True))
        ids.extend(
            FeedShelf.objects.values_list('description', flat=True))
        ids.extend(
            FeedShelf.objects.values_list('name', flat=True))
        ids.extend(
            FeedApp.objects.values_list('description', flat=True))
        ids.extend(
            FeedApp.objects.values_list('pullquote_text', flat=True))
        ids.extend(
            Version.objects.values_list('releasenotes', flat=True))
        ids.extend(
            Webapp.objects.values_list('description', flat=True))
        ids.extend(
            Webapp.objects.values_list('privacy_policy', flat=True))

        # Filter out any None's.
        ids = filter(None, ids)

        for chunk in chunked(ids, 100):
            update_translations.delay(chunk)
