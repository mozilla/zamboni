import logging

from django.conf import settings
from django.db import models

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
    # An abuse report can be for an addon, a user, or a website. Only one of
    # these should be set.
    addon = models.ForeignKey(Webapp, null=True, related_name='abuse_reports')
    user = models.ForeignKey(UserProfile, null=True,
                             related_name='abuse_reports')
    website = models.ForeignKey(Website, null=True,
                                related_name='abuse_reports')
    message = models.TextField()
    read = models.BooleanField(default=False)

    class Meta:
        db_table = 'abuse_reports'

    @property
    def object(self):
        return self.addon or self.user or self.website

    def send(self):
        obj = self.object
        if self.reporter:
            user_name = '%s (%s)' % (self.reporter.name, self.reporter.email)
        else:
            user_name = 'An anonymous coward'

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
            subject = u'[%s] Abuse Report for %s' % (type_, obj.name)
            recipient_list = (settings.ABUSE_EMAIL,)

        msg = u'%s reported an issue for %s (%s%s).\n\n%s' % (
            user_name, obj.name, settings.SITE_URL, obj.get_url_path(),
            self.message)
        send_mail(subject, msg, recipient_list=recipient_list)

    @classmethod
    def recent_high_abuse_reports(cls, threshold, period, addon_id=None):
        """
        Returns AbuseReport objects for the given threshold over the given time
        period (in days). Filters by addon_id if provided.

        E.g. Greater than 5 abuse reports for all webapps in the past 7 days.
        """
        abuse_sql = ['''
            SELECT `abuse_reports`.*,
                   COUNT(`abuse_reports`.`addon_id`) AS `num_reports`
            FROM `abuse_reports`
            INNER JOIN `addons` ON (`abuse_reports`.`addon_id` = `addons`.`id`)
            WHERE `abuse_reports`.`created` >= %s ''']
        params = [period]
        if addon_id:
            abuse_sql.append('AND `addons`.`id` = %s ')
            params.append(addon_id)
        abuse_sql.append('GROUP BY addon_id HAVING num_reports > %s')
        params.append(threshold)

        return list(cls.objects.raw(''.join(abuse_sql), params))


def send_abuse_report(request, obj, message):
    report = AbuseReport(ip_address=request.META.get('REMOTE_ADDR'),
                         message=message)
    if request.user.is_authenticated():
        report.reporter = request.user
    if isinstance(obj, Webapp):
        report.addon = obj
    elif isinstance(obj, UserProfile):
        report.user = obj
    elif isinstance(obj, Website):
        report.website = obj
    report.save()
    report.send()

    # Trigger addon high abuse report detection task.
    if isinstance(obj, Webapp):
        from mkt.webapps.tasks import find_abuse_escalations
        find_abuse_escalations.delay(obj.id)
