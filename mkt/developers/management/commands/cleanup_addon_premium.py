from django.core.management.base import BaseCommand

import mkt
from mkt.webapps.models import AddonPremium


class Command(BaseCommand):
    help = 'Clean up existing AddonPremium objects for free apps.'

    def handle(self, *args, **options):
        (AddonPremium.objects.filter(addon__premium_type__in=mkt.ADDON_FREES)
                             .delete())
