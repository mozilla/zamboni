from optparse import make_option

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand

import mkt
from mkt.files.models import File

HELP = 'List all Marketplace packaged apps'


statuses = {'pending': mkt.STATUS_PENDING,
            'public': mkt.STATUS_PUBLIC,
            'approved': mkt.STATUS_APPROVED,
            'rejected': mkt.STATUS_DISABLED}


class Command(BaseCommand):
    """
    Usage:

        python manage.py list_packaged_apps --status=<status>

    """

    option_list = BaseCommand.option_list + (
        make_option('--status',
                    choices=statuses.keys(),
                    help='Status of packaged-app files'),
    )

    help = HELP

    def handle(self, *args, **kwargs):
        files = File.objects.filter(version__addon__is_packaged=True)
        if kwargs.get('status'):
            files = files.filter(status=statuses[kwargs['status']])

        filenames = []

        for f in files:
            try:
                filenames.append(f.file_path)
            except ObjectDoesNotExist:
                pass

        print '\n'.join(filenames)
