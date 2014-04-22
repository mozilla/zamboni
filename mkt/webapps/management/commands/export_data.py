from django.core.management.base import BaseCommand

from mkt.webapps.tasks import export_data


class Command(BaseCommand):
    help = 'Export our data as a tgz for third-parties'

    def handle(self, *args, **kwargs):
        # Execute as a celery task so we get the right permissions.
        export_data.delay()
