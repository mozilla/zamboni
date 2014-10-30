from django.core.management.base import BaseCommand

from amo.utils import chunked
from mkt.comm.tasks import _migrate_approval_notes
from mkt.versions.models import Version


class Command(BaseCommand):
    help = ('Port version approvalnotes to notes with type '
            'DEVELOPER_VERSION_NOTE_FOR_REVIEWER.')

    def handle(self, *args, **options):
        ids = Version.objects.filter(approvalnotes__isnull=False)

        for log_chunk in chunked(ids, 100):
            _migrate_approval_notes.delay(ids)
