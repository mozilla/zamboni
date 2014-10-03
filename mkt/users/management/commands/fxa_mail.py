from optparse import make_option

from django.core.management.base import BaseCommand


from amo.utils import chunked
from mkt.constants.base import LOGIN_SOURCE_FXA
from mkt.users.models import UserProfile
from mkt.users.tasks import fxa_email_types, send_fxa_mail
from mkt.webapps.models import AddonUser


def get_user_ids(is_developers):
    developer_ids = (AddonUser.objects
                     .values_list('user_id', flat=True)
                     .distinct())
    if is_developers:
        return list(developer_ids.exclude(user__source=LOGIN_SOURCE_FXA))

    user_ids = (UserProfile.objects
                .exclude(source=LOGIN_SOURCE_FXA)
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

        ids = get_user_ids(is_developers)

        print 'Sending: {0} emails'.format(len(ids))
        for users in chunked(ids, 100):
            send_fxa_mail.delay(ids, mail_type, is_live)
