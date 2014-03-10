import logging

from django.core.management.base import BaseCommand

import amo

from mkt import regions


log = logging.getLogger('z.task')


class Command(BaseCommand):
    help = ('Remove game-related AERs for Brazil + Germany.')

    def handle(self, *args, **options):
        # Avoid import error.
        from mkt.webapps.models import Webapp

        games = Webapp.objects.filter(
            category__type=amo.ADDON_WEBAPP, category__slug='games')

        for app in games:
            aers = app.addonexcludedregion

            if (aers.count() == 2 and
                aers.filter(region=regions.BR.id).exists() and
                aers.filter(region=regions.DE.id).exists()):

                log.info('Removing BR/DE AERs for %s' % app.id)
                aers.all().delete()
