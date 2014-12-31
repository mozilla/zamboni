from django.core.management.base import BaseCommand

import commonware.log

from mkt.comm.tasks import _fix_developer_version_notes
from mkt.comm.models import CommunicationNote
from mkt.constants import comm
from mkt.site.utils import chunked


log = commonware.log.getLogger('comm')


class Command(BaseCommand):
    help = ('Fix developer version notes that were accidentally logged as '
            'reviewer comments due to "approvalnotes" being a confusing '
            'variable name')

    def handle(self, *args, **options):
        ids = (CommunicationNote.objects
                                .filter(note_type=comm.REVIEWER_COMMENT)
                                .values_list('id', flat=True))

        for log_chunk in chunked(ids, 100):
            _fix_developer_version_notes.delay(ids)
