import logging

from django.db import models

from mkt.extensions.models import Extension
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


# Add index on `created`.
AbuseReport._meta.get_field('created').db_index = True
