from django.core.management.base import BaseCommand

import commonware.log

import amo
from amo.utils import chunked
from devhub.models import ActivityLog, AppLog

from mkt.comm.tasks import _migrate_activity_log


log = commonware.log.getLogger('comm')


class Command(BaseCommand):
    help = ('Migrates ActivityLog objects to CommunicationNote objects. '
            'Meant for one time run only.')

    def handle(self, *args, **options):
        applog_ids = AppLog.objects.values_list('activity_log', flat=True)

        ids = (ActivityLog.objects.filter(
            pk__in=list(applog_ids), action__in=amo.LOG_REVIEW_QUEUE)
            .order_by('created').values_list('id', flat=True))

        for log_chunk in chunked(ids, 100):
            _migrate_activity_log.delay(ids)
