# -*- coding: utf-8 -*-
from django.conf import settings
from django.db import models
from django.dispatch import receiver

import json_field

from mkt.site.models import ModelBase
from mkt.tags.models import Tag
from mkt.translations.fields import save_signal, TranslatedField
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
    # FIXME status

    @classmethod
    def get_fallback(cls):
        return cls._meta.get_field('default_locale')

    @classmethod
    def get_indexer(self):
        return WebsiteIndexer

    def __unicode__(self):
        return unicode(self.url or '(no url set)')


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
