# -*- coding: utf-8 -*-
import os.path

from django.conf import settings
from django.db import models
from django.dispatch import receiver

from django_extensions.db.fields.json import JSONField

from lib.utils import static_url
from mkt.constants.applications import DEVICE_TYPES
from mkt.constants.base import LISTED_STATUSES, STATUS_CHOICES, STATUS_NULL
from mkt.site.models import ManagerBase, ModelBase
from mkt.site.utils import get_icon_url
from mkt.tags.models import Tag
from mkt.translations.fields import save_signal, TranslatedField
from mkt.translations.utils import no_translation
from mkt.websites.indexers import WebsiteIndexer


class WebsiteManager(ManagerBase):
    def valid(self):
        return self.filter(status__in=LISTED_STATUSES, is_disabled=False)


class Website(ModelBase):
    default_locale = models.CharField(max_length=10,
                                      default=settings.LANGUAGE_CODE)
    url = models.URLField(max_length=255, blank=True, null=True)
    mobile_url = models.URLField(max_length=255, blank=True, null=True)
    title = TranslatedField()
    name = TranslatedField()
    short_name = TranslatedField()
    description = TranslatedField()
    keywords = models.ManyToManyField(Tag)
    region_exclusions = JSONField(default=None)
    devices = JSONField(default=None)
    categories = JSONField(default=None)
    icon_type = models.CharField(max_length=25, blank=True)
    icon_hash = models.CharField(max_length=8, blank=True)
    last_updated = models.DateTimeField(db_index=True, auto_now_add=True)
    status = models.PositiveIntegerField(
        choices=STATUS_CHOICES.items(), default=STATUS_NULL)
    is_disabled = models.BooleanField(default=False)

    objects = WebsiteManager()

    class Meta:
        ordering = (('-last_updated'), )

    @classmethod
    def get_fallback(cls):
        return cls._meta.get_field('default_locale')

    @classmethod
    def get_indexer(self):
        return WebsiteIndexer

    def __unicode__(self):
        return unicode(self.url or '(no url set)')

    @property
    def device_names(self):
        device_ids = self.devices or []
        with no_translation():
            return [DEVICE_TYPES[d].api_name for d in device_ids]

    def is_dummy_content_for_qa(self):
        """
        Returns whether this app is a dummy app used for testing only or not.
        """
        # Change this when we start having dummy websites for QA purposes, see
        # Webapp implementation.
        return False

    def get_icon_dir(self):
        return os.path.join(settings.WEBSITE_ICONS_PATH, str(self.pk / 1000))

    def get_icon_url(self, size):
        return get_icon_url(static_url('WEBSITE_ICON_URL'), self, size)


class WebsitePopularity(ModelBase):
    website = models.ForeignKey(Website, related_name='popularity')
    value = models.FloatField(default=0.0)
    # When region=0, we count across all regions.
    region = models.PositiveIntegerField(null=False, default=0, db_index=True)

    class Meta:
        db_table = 'websites_popularity'
        unique_together = ('website', 'region')


class WebsiteTrending(ModelBase):
    website = models.ForeignKey(Website, related_name='trending')
    value = models.FloatField(default=0.0)
    # When region=0, it's trending using install counts across all regions.
    region = models.PositiveIntegerField(null=False, default=0, db_index=True)

    class Meta:
        db_table = 'websites_trending'
        unique_together = ('website', 'region')


# Maintain ElasticSearch index.
@receiver(models.signals.post_save, sender=Website,
          dispatch_uid='website_index')
def update_search_index(sender, instance, **kw):
    instance.get_indexer().index_ids([instance.id])


# Delete from ElasticSearch index on delete.
@receiver(models.signals.post_delete, sender=Website,
          dispatch_uid='website_unindex')
def delete_search_index(sender, instance, **kw):
    instance.get_indexer().unindex(instance.id)


# Save translations before saving Website instance with translated fields.
models.signals.pre_save.connect(save_signal, sender=Website,
                                dispatch_uid='website_translations')
