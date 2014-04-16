from django.core.management.base import BaseCommand

from mkt.webapps.tasks import export_data


class Command(BaseCommand):
    help = 'Export our data as a tgz for third-parties'

    def handle(self, *args, **kwargs):
        export_data()
