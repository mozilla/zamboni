import logging
import re

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

import commonware.log

from mkt.site.models import FakeEmail
from mkt.site.tasks import send_email
from mkt.site.utils import env
from mkt.users.models import UserNotification
from mkt.users.notifications import NOTIFICATIONS_BY_SHORT
from mkt.zadmin.models import get_config


maillog = logging.getLogger('z.mkt.mail')
log = commonware.log.getLogger('z.mkt')


class FakeEmailBackend(BaseEmailBackend):
    """
    Used for development environments when we don't want to send out
    real emails. This gets swapped in as the email backend when
    `settings.SEND_REAL_EMAIL` is disabled.
    """

    def send_messages(self, messages):
        """Sends a list of messages (saves `FakeEmail` objects)."""
        maillog.debug('Sending fake mail.')
        for msg in messages:
            FakeEmail.objects.create(message=msg.message().as_string())
        return len(messages)

    def view_all(self):
        """Useful for displaying messages in admin panel."""
        return (FakeEmail.objects.values_list('message', flat=True)
                .order_by('-created'))

    def clear(self):
        return FakeEmail.objects.all().delete()


def send_mail(subject, message, from_email=None, recipient_list=None,
              fail_silently=False, use_blocked=True, perm_setting=None,
              manage_url=None, headers=None, cc=None,
              html_message=None, attachments=None, async=False,
              max_retries=None):
    """
    A wrapper around django.core.mail.EmailMessage.

    Adds blocked emails checking and error logging.
    """
    if not recipient_list:
        return True

    if isinstance(recipient_list, basestring):
        raise ValueError('recipient_list should be a list, not a string.')

    # Check against user notification settings
    if perm_setting:
        if isinstance(perm_setting, str):
            perm_setting = NOTIFICATIONS_BY_SHORT[perm_setting]
        perms = dict(UserNotification.objects
                                     .filter(user__email__in=recipient_list,
                                             notification_id=perm_setting.id)
                                     .values_list('user__email', 'enabled'))

        d = perm_setting.default_checked
        recipient_list = [e for e in recipient_list
                          if e and perms.setdefault(e, d)]

    # Prune blocked emails.
    if use_blocked:
        not_blocked = []
        for email in recipient_list:
            if email and email.lower() in settings.EMAIL_BLOCKED:
                log.debug('Blocked email removed from list: %s' % email)
            else:
                not_blocked.append(email)
        recipient_list = not_blocked

    # We're going to call send_email twice, once for fake emails, the other
    # real.
    if settings.SEND_REAL_EMAIL:
        # Send emails out to all recipients.
        fake_recipient_list = []
        real_recipient_list = recipient_list
    else:
        # SEND_REAL_EMAIL is False so need to split out the fake from real
        # mails.
        real_email_regexes = _real_email_regexes()
        if real_email_regexes:
            fake_recipient_list = []
            real_recipient_list = []
            for email in recipient_list:
                if email and any(regex.match(email.lower())
                                 for regex in real_email_regexes):
                    log.debug('Real email encountered: %s - sending.' % email)
                    real_recipient_list.append(email)
                else:
                    fake_recipient_list.append(email)
        else:
            # No filtered list in the config so all emails are fake.
            fake_recipient_list = recipient_list
            real_recipient_list = []

    if not from_email:
        from_email = settings.DEFAULT_FROM_EMAIL

    if cc:
        # If not basestring, assume it is already a list.
        if isinstance(cc, basestring):
            cc = [cc]

    if not headers:
        headers = {}

    def send(recipient, message, real_email, **options):
        kwargs = {
            'async': async,
            'attachments': attachments,
            'cc': cc,
            'fail_silently': fail_silently,
            'from_email': from_email,
            'headers': headers,
            'html_message': html_message,
            'max_retries': max_retries,
            'real_email': real_email,
        }
        kwargs.update(options)
        # Email subject *must not* contain newlines
        args = (recipient, ' '.join(subject.splitlines()), message)
        if async:
            return send_email.delay(*args, **kwargs)
        else:
            return send_email(*args, **kwargs)

    if fake_recipient_list:
        # Send fake emails to these recipients (i.e. don't actually send them).
        result = send(fake_recipient_list, message=message, real_email=False,
                      html_message=html_message, attachments=attachments)
    else:
        result = True

    if result and real_recipient_list:
        # And then send emails out to these recipients.
        result = send(real_recipient_list, message=message, real_email=True,
                      html_message=html_message, attachments=attachments)

    return result


def send_mail_jinja(subject, template, context, *args, **kwargs):
    """Sends mail using a Jinja template with autoescaping turned off.

    Jinja is especially useful for sending email since it has whitespace
    control.
    """
    # Get a jinja environment so we can override autoescaping for text emails.
    autoescape_orig = env.autoescape
    env.autoescape = False
    template = env.get_template(template)
    msg = send_mail(subject, template.render(context), *args, **kwargs)
    env.autoescape = autoescape_orig
    return msg


def send_html_mail_jinja(subject, html_template, text_template, context,
                         *args, **kwargs):
    """Sends HTML mail using a Jinja template with autoescaping turned off."""
    autoescape_orig = env.autoescape
    env.autoescape = False

    html_template = env.get_template(html_template)
    text_template = env.get_template(text_template)

    msg = send_mail(subject, text_template.render(context),
                    html_message=html_template.render(context), *args,
                    **kwargs)

    env.autoescape = autoescape_orig

    return msg


def _real_email_regexes():
    real_email_regexes = get_config('real_email_allowed_regex')
    # We have a list set in the config so use it.
    if real_email_regexes:
        regexes = []
        for regex in real_email_regexes.split(','):
            try:
                regexes.append(re.compile(regex.strip().lower()))
            except re.error:
                pass
        return regexes
    else:
        return []
