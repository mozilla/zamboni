from optparse import make_option

from django.core.management.base import BaseCommand

from mkt.webapps.tasks import generate_apps

class Command(BaseCommand):
    """
    Usage:

        python manage.py generate_apps <amount>

    """

    help = 'Generate example apps for development/testing'

    def handle(self, *args, **kwargs):
        num = int(args[0])
        generate_apps(num)
