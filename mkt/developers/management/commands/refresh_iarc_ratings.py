import logging
from optparse import make_option

from django.core.management.base import BaseCommand

from mkt.developers.tasks import refresh_iarc_ratings
from mkt.site.utils import chunked


log = logging.getLogger('z.task')


class Command(BaseCommand):
    """
    Refresh old or corrupt IARC ratings by re-fetching the certificate.
    """
    option_list = BaseCommand.option_list + (
        make_option('--apps',
                    help='Webapp ids to process. Use commas to separate '
                         'multiple ids.'),
    )
    help = __doc__

    def handle(self, *args, **kw):
        from mkt.webapps.models import Webapp

        # Get apps.
        apps = Webapp.objects.filter(iarc_cert__isnull=False)
        ids = kw.get('apps')
        if ids:
            apps = apps.filter(
                id__in=(int(id.strip()) for id in ids.split(',')))

        for chunk in chunked(apps.values_list('id', flat=True), 100):
            refresh_iarc_ratings.delay(chunk)
