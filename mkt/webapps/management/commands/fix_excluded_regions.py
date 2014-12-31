from optparse import make_option

from django.core.management.base import BaseCommand

from mkt.site.utils import chunked
from mkt.webapps.models import Webapp
from mkt.webapps.tasks import fix_excluded_regions


HELP = """\
    Usage:

        python manage.py fix_excluded_regions [--app=<app_id>]

    If no --app provided, all unrestricted apps are processed.
"""


class Command(BaseCommand):
    help = HELP

    option_list = BaseCommand.option_list + (
        make_option('--app', help='The app ID to process'),
    )

    def handle(self, *args, **kwargs):
        qs = Webapp.objects.filter(_geodata__restricted=False)

        if kwargs['app']:
            qs = qs.filter(pk=kwargs['app'])

        apps = qs.values_list('id', flat=True)
        for chunk in chunked(apps, 100):
            fix_excluded_regions.delay(chunk)
