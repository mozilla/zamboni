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
    args = '<JSON spec filename>'

    def handle(self, *args, **kwargs):
        if len(args) < 1:
            raise CommandError('Provide a spec filename.')

        specs = json.load(open(args[0]))
        generate_apps_from_specs(specs,
                                 os.path.abspath(os.path.dirname(args[0])))
