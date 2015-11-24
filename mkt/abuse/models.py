import logging

from django.conf import settings
from django.db import models

from mkt.extensions.models import Extension
from mkt.site.mail import send_mail
from mkt.site.models import ModelBase
from mkt.users.models import UserProfile
from mkt.webapps.models import Webapp
from mkt.websites.models import Website


log = logging.getLogger('z.abuse')


class AbuseReport(ModelBase):
    # NULL if the reporter is anonymous.
    reporter = models.ForeignKey(UserProfile, null=True,
                                 blank=True, related_name='abuse_reported')
    ip_address = models.CharField(max_length=255, default='0.0.0.0')
    # An abuse report can be for an app, a user, a website, or an extension.
    # Only one of these should be set.
    addon = models.ForeignKey(Webapp, null=True, related_name='abuse_reports')
    user = models.ForeignKey(UserProfile, null=True,
                             related_name='abuse_reports')
    website = models.ForeignKey(Website, null=True,
                                related_name='abuse_reports')
    extension = models.ForeignKey(Extension, null=True,
                                  related_name='abuse_reports')
    message = models.TextField()
    read = models.BooleanField(default=False)

    class Meta:
        db_table = 'abuse_reports'

    @property
    def object(self):
        return self.addon or self.user or self.website or self.extension

    def send(self):
        obj = self.object
        if self.reporter:
            user_name = '%s (%s)' % (self.reporter.name, self.reporter.email)
        else:
            user_name = 'An anonymous user'

        if self.website:
            # For Websites, it's not just abuse, the scope is broader, it could
            # be any issue about the website listing itself, so use a different
            # wording and recipient list.
            type_ = u'Website'
            subject = u'[%s] Issue Report for %s' % (type_, obj.name)
            recipient_list = (settings.MKT_FEEDBACK_EMAIL,)
        else:
            if self.addon:
                type_ = 'App'
            elif self.user:
                type_ = 'User'
            elif self.extension:
                type_ = 'FxOS Add-on'
            subject = u'[%s] Abuse Report for %s' % (type_, obj.name)
            recipient_list = (settings.ABUSE_EMAIL,)

        msg = u'%s reported an issue for %s (%s%s).\n\n%s' % (
            user_name, obj.name, settings.SITE_URL, obj.get_url_path(),
            self.message)
        send_mail(subject, msg, recipient_list=recipient_list)


# Add index on `created`.
AbuseReport._meta.get_field('created').db_index = True
