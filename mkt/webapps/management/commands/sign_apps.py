import logging
import sys
from optparse import make_option

from django.core.management.base import BaseCommand

from celery.task.sets import TaskSet

import mkt
from lib.crypto.packaged import sign
from mkt.webapps.models import Webapp


HELP = """\
Start tasks to re-sign web apps.

To specify which webapps to sign:

    `--webapps=1234,5678,...9012`

If omitted, all signed apps will be re-signed.
"""


log = logging.getLogger('z.addons')


class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option('--webapps',
                    help='Webapp ids to process. Use commas to separate '
                         'multiple ids.'),
    )

    help = HELP

    def handle(self, *args, **kw):
        qs = Webapp.objects.filter(is_packaged=True,
                                   status__in=mkt.LISTED_STATUSES)
        if kw['webapps']:
            pks = [int(a.strip()) for a in kw['webapps'].split(',')]
            qs = qs.filter(pk__in=pks)

        tasks = []
        for app in qs:
            if not app.current_version:
                sys.stdout.write('Public app [id:%s] with no current version'
                                 % app.pk)
                continue

            tasks.append(sign.subtask(args=[app.current_version.pk],
                                      kwargs={'resign': True}))
        TaskSet(tasks).apply_async()
