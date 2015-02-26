from django.core.management.base import BaseCommand

from mkt.feed.fakedata import generate_feed_data


class Command(BaseCommand):
    """
    Usage:

        python manage.py generate_feed

    """

    help = 'Generate example feed data for development/testing'

    def handle(self, *args, **kwargs):
        generate_feed_data()
