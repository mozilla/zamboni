import json

from django.conf import settings
from django.db import models
from django.utils.functional import memoize

from mkt.site.models import ModelBase


_config_cache = {}


class Config(models.Model):
    """Sitewide settings."""
    key = models.CharField(max_length=255, primary_key=True)
    value = models.TextField()

    class Meta:
        db_table = u'config'

    @property
    def json(self):
        try:
            return json.loads(self.value)
        except (TypeError, ValueError):
            return {}


def unmemoized_get_config(conf):
    try:
        c = Config.objects.get(key=conf)
        return c.value
    except Config.DoesNotExist:
        return

get_config = memoize(unmemoized_get_config, _config_cache, 1)


def set_config(conf, value):
    cf, created = Config.objects.get_or_create(key=conf)
    cf.value = value
    cf.save()
    _config_cache.clear()


class EmailPreviewTopic(object):
    """Store emails in a given topic so an admin can preview before
    re-sending.

    A topic is a unique string identifier that groups together preview emails.
    If you pass in an object (a Model instance) you will get a poor man's
    foreign key as your topic.

    For example, EmailPreviewTopic(addon) will link all preview emails to
    the ID of that addon object.
    """

    def __init__(self, object=None, suffix='', topic=None):
        if not topic:
            assert object, 'object keyword is required when topic is empty'
            topic = '%s-%s-%s' % (object.__class__._meta.db_table, object.pk,
                                  suffix)
        self.topic = topic

    def filter(self, *args, **kw):
        kw['topic'] = self.topic
        return EmailPreview.objects.filter(**kw)

    def send_mail(self, subject, body,
                  from_email=settings.DEFAULT_FROM_EMAIL,
                  recipient_list=tuple([])):
        return EmailPreview.objects.create(
            topic=self.topic,
            subject=subject, body=body,
            recipient_list=u','.join(recipient_list),
            from_email=from_email)


class EmailPreview(ModelBase):
    """A log of emails for previewing purposes.

    This is only for development and the data might get deleted at any time.
    """
    topic = models.CharField(max_length=255, db_index=True)
    recipient_list = models.TextField()  # comma separated list of emails
    from_email = models.EmailField()
    subject = models.CharField(max_length=255)
    body = models.TextField()

    class Meta:
        db_table = 'email_preview'
