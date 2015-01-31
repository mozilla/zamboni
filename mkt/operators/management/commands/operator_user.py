from optparse import make_option

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from mkt.carriers import CARRIER_CHOICE_DICT, CARRIER_MAP
from mkt.operators.models import OperatorPermission
from mkt.regions import REGIONS_CHOICES_ID_DICT, REGIONS_DICT
from mkt.users.models import UserProfile

all_opt = make_option('--all', action='store_true', dest='remove_all',
                      default=False,
                      help='Remove all operator permissions for the user')


class Command(BaseCommand):
    args = '[command] [command_options]'
    option_list = BaseCommand.option_list + (all_opt,)
    help = ('Add, remove, or list operator permissions for a user:\n\n'
            'manage.py operator_user add <email> <carrier> <region>\n'
            'manage.py operator_user remove <email> <carrier> <region>\n'
            'manage.py operator_user remove --all <email>\n'
            'manage.py operator_user list <email>')

    def get_user(self, email):
        try:
            return UserProfile.objects.get(email=email)
        except UserProfile.DoesNotExist:
            raise CommandError('No user account for: %s' % email)

    def get_region_id(self, slug):
        try:
            return REGIONS_DICT[slug].id
        except KeyError:
            raise CommandError('Invalid region: %r' % slug)

    def get_carrier_id(self, slug):
        try:
            return CARRIER_MAP[slug].id
        except KeyError:
            raise CommandError('Invalid carrier: %r' % slug)

    def get_region_slug(self, id):
        try:
            return REGIONS_CHOICES_ID_DICT[id].slug
        except KeyError:
            raise CommandError('Invalid region: %r' % id)

    def get_carrier_slug(self, id):
        try:
            return CARRIER_CHOICE_DICT[id].slug
        except KeyError:
            raise CommandError('Invalid carrier: %r' % id)

    def get_ecr(self, args):
        sliced = args[1:]
        if not len(sliced) == 3:
            raise CommandError('Did not pass <email> <carrier> <region>')
        return sliced

    def handle(self, *args, **options):
        try:
            cmd = args[0]
        except IndexError:
            raise CommandError('No command passed.')

        if cmd == 'add':
            email, carrier, region = self.get_ecr(args)
            try:
                OperatorPermission.objects.create(
                    user=self.get_user(email),
                    region=self.get_region_id(region),
                    carrier=self.get_carrier_id(carrier))
                self.stdout.write('Created %s/%s permission for %s' % (
                    region, carrier, email))
            except DatabaseError, e:
                exception = CommandError('Unable to grant permission.')
                exception.args = e.args
                raise exception

        elif cmd == 'remove':

            if options['remove_all']:
                user = self.get_user(args[1])
                qs = OperatorPermission.objects.filter(user=user)
                if len(qs):
                    qs.delete()
                    self.stdout.write('Removed all permissions for %s'
                                      % args[1])
                else:
                    raise CommandError('No permissions for %s' % args[1])

            else:
                email, carrier, region = self.get_ecr(args)
                qs = OperatorPermission.objects.filter(
                    user=self.get_user(email),
                    region=self.get_region_id(region),
                    carrier=self.get_carrier_id(carrier))
                if len(qs):
                    qs.delete()
                    self.stdout.write('Removed %s/%s permission for %s' % (
                        region, carrier, email))
                else:
                    raise CommandError('No %s/%s permission for %s' % (
                        region, carrier, email))

        elif cmd == 'list':
            user = self.get_user(args[1])
            qs = OperatorPermission.objects.filter(user=user)
            if len(qs):
                msg = ['Permissions for %s:' % args[1]]
                for item in qs:
                    msg.append('- %s/%s' % (
                        self.get_region_slug(item.region),
                        self.get_carrier_slug(item.carrier),
                    ))
                self.stdout.write('\n'.join(msg))
            else:
                self.stdout.write('No permissions for %s' % args[1])

        else:
            raise CommandError('Invalid command: %s' % cmd)
