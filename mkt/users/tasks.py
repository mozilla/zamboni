from datetime import timedelta

import commonware.log
from celeryutils import task

from django.utils.encoding import force_text

from tower import ugettext_lazy as _

from mkt.account.utils import fxa_preverify_url
from mkt.site.mail import send_html_mail_jinja
from mkt.users.models import UserProfile

fxa_email_subjects = {
    'customers-before': _('Firefox Accounts is coming'),
    'customers-during': _('Activate your Firefox Account'),
    'customers-after': _('Activate your Firefox Account'),
    'developers-before': _('Firefox Accounts is coming'),
    'developers-during': _('Activate your Firefox Account'),
    'developers-after': _('Activate your Firefox Account')
}
fxa_email_types = fxa_email_subjects.keys()
log = commonware.log.getLogger('z.users')


@task
def send_mail(user_ids, subject, html_template, text_template, link):
    for user in UserProfile.objects.filter(pk__in=user_ids):
        if not user.email:
            log.info('Skipping: {0}, no email'.format(user.pk))
            continue

        context = {'title': subject}
        if link:
            context['link'] = fxa_preverify_url(user, timedelta(days=7))

        with user.activate_lang():
            log.info('Sending FxA transition email to: {0} (id={1})'
                     .format(user.email, user.pk))
            send_html_mail_jinja(
                force_text(subject),
                html_template, text_template,
                context, recipient_list=[user.email])


@task
def send_fxa_mail(user_ids, mail_type, send_link):
    return send_mail(
        user_ids,
        fxa_email_subjects[mail_type],
        'users/emails/{0}.html'.format(mail_type),
        'users/emails/{0}.ltxt'.format(mail_type),
        send_link)
