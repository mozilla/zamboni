import json
import os

from django.core.management.base import BaseCommand

from mkt.users.utils import create_user


class Command(BaseCommand):
    help = """Create users from JSON data.
           """
    args = '<path to directory containing JSON files>'

    def handle(self, *args, **kw):
        files = os.listdir(args[0])
        for n in files:
            fn = os.path.join(args[0], n)
            if not fn.endswith('.json'):
                continue
            with open(fn) as f:
                print 'Loading', fn
                create_user(**json.load(f))
