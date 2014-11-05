from datetime import datetime
from optparse import make_option

from django.core.management.base import BaseCommand

import commonware.log

from amo.utils import chunked
from mkt.constants.base import LOGIN_SOURCE_FXA
from mkt.users.models import UserProfile
from mkt.users.tasks import fxa_email_types, send_fxa_mail
from mkt.webapps.models import AddonUser

log = commonware.log.getLogger('z.users')


def get_user_ids(is_developers):
    developer_ids = (AddonUser.objects
                     .filter(user__last_login_attempt__gt=datetime(2014, 4, 30))
                     .values_list('user_id', flat=True)
                     .distinct())
    if is_developers:
        return list(developer_ids.exclude(user__source=LOGIN_SOURCE_FXA))

    user_ids = (UserProfile.objects
                .exclude(source=LOGIN_SOURCE_FXA)
                .filter(last_login_attempt__gt=datetime(2014, 4, 30))
                .values_list('id', flat=True))
    return list(set(user_ids).difference(set(developer_ids)))


class Command(BaseCommand):
    """
    A temporary management command to send emails to people throughout
    the Firefox Accounts transition.

    Type must be one of the email choices as specfied in the emails dict above.
    """
    option_list = BaseCommand.option_list + (
        make_option('--type', action='store', type='string',
                    dest='type', help='Type of email to send.'),
    )

    def handle(self, *args, **kwargs):
        mail_type = kwargs.get('type')
        if mail_type not in fxa_email_types:
            raise ValueError('{0} email not known.'.format(mail_type))

        audience, phase = mail_type.split('-')
        is_live = phase in ['during', 'after']
        is_developers = audience == 'developers'

        all_ids = get_user_ids(is_developers)

        log.info('Sending: {0} {1} emails'.format(len(all_ids), mail_type))
        for chunked_ids in chunked(all_ids, 100):
            send_fxa_mail.delay(chunked_ids, mail_type, is_live)
