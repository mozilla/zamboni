import json

from django.core.management.base import BaseCommand

from mkt.users.utils import create_user


class Command(BaseCommand):
    help = """Create users from JSON data.
           """
    args = '<JSON filename>'

    def handle(self, *args, **kw):
        with open(args[0]) as f:
            for data in json.load(f):
                create_user(**data)
