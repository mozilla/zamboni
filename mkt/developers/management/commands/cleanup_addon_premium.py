from django.core.management.base import BaseCommand

import mkt
from mkt.webapps.models import WebappPremium


class Command(BaseCommand):
    help = 'Clean up existing WebappPremium objects for free apps.'

    def handle(self, *args, **options):
        (WebappPremium.objects.filter(
            webapp__premium_type__in=mkt.WEBAPP_FREES)
         .delete())
