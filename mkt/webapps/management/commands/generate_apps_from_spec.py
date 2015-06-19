import os.path
import json

from django.core.management.base import BaseCommand, CommandError

from mkt.webapps.fakedata import generate_apps_from_specs


class Command(BaseCommand):
    """
    Usage:

        python manage.py generate_apps_from_spec <JSON spec file>

    """

    help = 'Generate example apps for QA'
    args = '<JSON spec filename> <number of repeats> <name prefix>'

    def handle(self, *args, **kwargs):
        if len(args) < 1:
            raise CommandError('Provide a spec filename.')

        specs = json.load(open(args[0]))
        repeats = 0
        if (len(args) > 1):
            repeats = int(args[1])
        if (len(args) > 2):
            prefix = str(args[2])
        else:
            prefix = ''
        generate_apps_from_specs(specs,
                                 os.path.abspath(os.path.dirname(args[0])),
                                 repeats,
                                 prefix)
