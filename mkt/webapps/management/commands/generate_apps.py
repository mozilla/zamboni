from optparse import make_option

from django.core.management.base import BaseCommand, CommandError

from mkt.webapps.tasks import generate_apps


class Command(BaseCommand):
    """
    Usage:

        python manage.py generate_apps <number of apps>

    """

    help = 'Generate example apps for development/testing'
    option_list = BaseCommand.option_list + (
        make_option('--type',
                    choices=['hosted', 'packaged'],
                    default='hosted',
                    help='Kind of apps to generate'),)

    def handle(self, *args, **kwargs):
        if len(args) < 1:
            raise CommandError("Number of apps required.")
        if kwargs['type'] == 'hosted':
            generate_apps(args[0], 0)
        else:
            generate_apps(0, args[0])
