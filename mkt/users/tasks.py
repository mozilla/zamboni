from celeryutils import task

from django.utils.encoding import force_text

from mkt.site.mail import send_html_mail_jinja
from mkt.users.models import UserProfile


@task
def send_mail(user_ids, subject, html_template, text_template, link):
    for user in UserProfile.objects.filter(pk__in=user_ids):
        if not user.email:
            print 'Skipping: {0}, no email'.format(user.pk)
            continue

        context = {'title': subject}
        if link:
            # TODO: the Pre-Verification API goes in here if relevant.
            context['link'] = 'https://marketplace.firefox.com'

        with user.activate_lang():
            send_html_mail_jinja(force_text(subject),
                html_template, text_template,
                context, recipient_list=[user.email])
