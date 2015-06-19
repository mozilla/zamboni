import os.path
import json

from django.core.management.base import BaseCommand, CommandError

from mkt.webapps.fakedata import generate_apps_from_specs


class Command(BaseCommand):
    """
    Usage:

        python manage.py generate_reviewer_apps <JSON spec file> <num of sets>

    """

    help = 'Generate sets of prefixed reviewer apps for onboarding'
    args = '<JSON spec filename> <number of sets>'

    def handle(self, *args, **kwargs):
        if len(args) < 1:
            raise CommandError('Provide a spec filename.')

        specs = json.load(open(args[0]))
        sets = 1
        if (len(args) > 1):
            sets = int(args[1])

        for x in xrange(sets):
            generate_apps_from_specs(
                specs,
                os.path.abspath(os.path.dirname(args[0])),
                0,
                '#%s - ' % x)
