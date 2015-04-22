from optparse import make_option

from django.core.management.base import BaseCommand, CommandError

from mkt.webapps.fakedata import generate_apps


class Command(BaseCommand):
    """
    Usage:

        python manage.py generate_apps <number of apps>

    """

    help = 'Generate example apps for development/testing'
    option_list = BaseCommand.option_list + (
        make_option('--type',
                    choices=['hosted', 'packaged', 'privileged'],
                    default='hosted',
                    help=('Kind of apps to generate: one of "hosted", '
                          '"packaged", or "privileged"')),
        make_option('--versions',
                    type='int',
                    default=1,
                    help='Number of public versions to generate for each app'))

    def handle(self, *args, **kwargs):
        if len(args) < 1:
            raise CommandError("Number of apps required.")
        num_apps = int(args[0])
        vs = ('public',) * kwargs['versions']
        if kwargs['type'] == 'hosted':
            generate_apps(hosted=num_apps, versions=vs)
        elif kwargs['type'] == 'packaged':
            generate_apps(packaged=num_apps, versions=vs)
        elif kwargs['type'] == 'privileged':
            generate_apps(privileged=num_apps, versions=vs)
