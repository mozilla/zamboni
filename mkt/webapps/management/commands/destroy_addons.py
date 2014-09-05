from optparse import make_option

from django.core.management.base import BaseCommand

import amo
from amo.utils import chunked
from mkt.webapps.models import Addon
from mkt.webapps.tasks import destroy_addons


HELP = """\
    Usage:

        python manage.py destroy_addons [--addon=<addon_id>]

    If no --addon provided, all add-ons are processed.

"""


class Command(BaseCommand):
    help = HELP

    option_list = BaseCommand.option_list + (
        make_option('--addon', help='The addon ID to purge'),
    )

    def handle(self, *args, **kwargs):
        # Especially don't delete webapps.
        qs = Addon.with_deleted.exclude(type=amo.ADDON_WEBAPP)

        if kwargs['addon']:
            qs = qs.filter(pk=kwargs['addon'])

        apps = qs.values_list('id', flat=True)
        for chunk in chunked(apps, 50):
            destroy_addons.delay(chunk)
