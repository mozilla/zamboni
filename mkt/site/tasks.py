from django.core.mail import EmailMessage, EmailMultiAlternatives, get_connection

import commonware.log
from celeryutils import task


log = commonware.log.getLogger('z.task')


@task
def send_email(recipient, subject, message, real_email, from_email=None,
               html_message=None, attachments=None,
               cc=None, headers=None, fail_silently=False, async=False,
               max_retries=None, **kwargs):
    email_backend = EmailMultiAlternatives if html_message else EmailMessage

    connection_backend = None if real_email else 'mkt.site.mail.FakeEmailBackend'
    connection = get_connection(connection_backend)
    result = email_backend(subject, message,
                           from_email, recipient, cc=cc, connection=connection,
                           headers=headers, attachments=attachments)
    if html_message:
        result.attach_alternative(html_message, 'text/html')
    try:
        result.send(fail_silently=False)
        return True
    except Exception as e:
        log.error('send_mail failed with error: %s' % e)
        if async:
            return send_email.retry(exc=e, max_retries=max_retries)
        elif not fail_silently:
            raise
        else:
            return False
