from optparse import make_option

from django.core.management.base import BaseCommand

from mkt.users.utils import create_user


class Command(BaseCommand):
    help = """Create users with different profiles (App Review, Admin,
              Developer, End User)
           """
    option_list = BaseCommand.option_list + (
        make_option(
            '--clear', action='store_true', dest='clear', default=False,
            help='Clear the user access tokens before recreating them'),)

    def handle(self, *args, **kw):
        options = {'password': 'fake_password'}

        if kw['clear']:
            options['overwrite'] = True

        create_user('appreviewer@mozilla.com', group_name='App Reviewers',
                    **options)
        create_user('admin@mozilla.com', group_name='Admins', **options)
        create_user('developer@mozilla.com', **options)
        create_user('enduser@mozilla.com', **options)
