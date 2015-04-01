# -*- coding: utf-8 -*-
from django.conf import settings
from django.db import models
from django.dispatch import receiver

import json_field

from mkt.constants.applications import DEVICE_TYPES
from mkt.constants.base import STATUS_PUBLIC
from mkt.site.models import ModelBase
from mkt.tags.models import Tag
from mkt.translations.fields import save_signal, TranslatedField
from mkt.translations.utils import no_translation
from mkt.websites.indexers import WebsiteIndexer


class Website(ModelBase):
    default_locale = models.CharField(max_length=10,
                                      default=settings.LANGUAGE_CODE)
    url = TranslatedField()
    title = TranslatedField()
    short_title = TranslatedField()
    description = TranslatedField()
    keywords = models.ManyToManyField(Tag)
    region_exclusions = json_field.JSONField(default=None)
    devices = json_field.JSONField(default=None)
    categories = json_field.JSONField(default=None)
    icon_type = models.CharField(max_length=25, blank=True)
    icon_hash = models.CharField(max_length=8, blank=True)
    last_updated = models.DateTimeField(db_index=True, auto_now_add=True)

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

    @property
    def status(self):
        # For now, all websites are public.
        # FIXME: add real field and migration.
        return STATUS_PUBLIC

    @property
    def is_disabled(self):
        # For now, all websites are enabled.
        # FIXME: add real field and migration.
        return False

    def get_boost(self):
        """
        Returns the boost used in Elasticsearch for this website.
        """
        return 1.0


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
