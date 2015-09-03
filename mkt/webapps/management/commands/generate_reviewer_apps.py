import os.path
import json
import random
import string

from django.core.management.base import BaseCommand, CommandError

from mkt.webapps.fakedata import generate_apps_from_specs


class Command(BaseCommand):
    """
    Usage:

        python manage.py generate_reviewer_apps <JSON spec file>
        <comma separated prefixes>

    """

    help = 'Generate sets of prefixed reviewer apps for onboarding'
    args = '<JSON spec filename> <comma separated prefixes>'

    def handle(self, *args, **kwargs):
        if len(args) < 1:
            raise CommandError('Provide a spec filename.')

        specs = json.load(open(args[0]))

        if (len(args) > 1):
            sets = args[1].split(',')
        else:
            sets = [''.join(random.choice(string.letters) for _ in range(3))]

        for prefix in sets:
            generate_apps_from_specs(
                specs,
                os.path.abspath(os.path.dirname(args[0])),
                0,
                '[%s] - ' % prefix)
