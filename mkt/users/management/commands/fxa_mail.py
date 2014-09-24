from optparse import make_option

from django.core.management.base import BaseCommand

from tower import ugettext_lazy as _

from amo.utils import chunked
from mkt.users.models import UserProfile
from mkt.users.tasks import send_mail
from mkt.webapps.models import AddonUser

emails = {
    'customers-before': _('Firefox Accounts is coming'),
    'customers-during': _('Activate your Firefox Account'),
    'customers-after': _('Activate your Firefox Account'),
    'developers-before': _('Firefox Accounts is coming'),
    'developers-during': _('Activate your Firefox Account'),
    'developers-after': _('Activate your Firefox Account')
}


class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option('--type', action='store', type='string',
                    dest='type', help='Type of email to send.'),
    )

    def handle(self, *args, **kwargs):
        mail_type = kwargs.get('type')
        if mail_type not in emails:
            raise ValueError('{0} email not known.'.format(mail_type))

        # There's probably a better way of figuring out who is a developer
        # and who is not.
        developer_ids = (AddonUser.objects.values_list('user_id', flat=True)
                         .distinct())
        if mail_type.split('-')[0] == 'developers':
            print 'Sending: developers'
            ids = developer_ids
        else:
            user_ids = UserProfile.objects.values_list('id', flat=True)
            print 'Sending: customers'
            ids = set(user_ids).difference(set(developer_ids))

        create_link = mail_type.split('-')[1] in ['during', 'after']

        print 'Sending: {0} emails'.format(len(ids))
        for users in chunked(ids, 100):
            send_mail.delay(
                ids,
                emails[mail_type],
                'users/emails/{0}.html'.format(mail_type),
                'users/emails/{0}.ltxt'.format(mail_type),
                create_link)
