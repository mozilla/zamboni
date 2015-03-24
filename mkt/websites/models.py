# -*- coding: utf-8 -*-
from django.conf import settings
from django.db import models

import json_field

from mkt.site.models import ModelBase
from mkt.translations.fields import TranslatedField
from mkt.tags.models import Tag
from mkt.translations.fields import save_signal


class Website(ModelBase):
    default_locale = models.CharField(max_length=10,
                                      default=settings.LANGUAGE_CODE)
    url = TranslatedField()
    title = TranslatedField()
    short_title = TranslatedField()
    description = TranslatedField()
    keywords = models.ManyToManyField(Tag)
    # FIXME regions
    categories = json_field.JSONField(default=None)
    icon_type = models.CharField(max_length=25, blank=True)
    icon_hash = models.CharField(max_length=8, blank=True)
    # FIXME devices
    last_updated = models.DateTimeField(db_index=True, auto_now_add=True)
    # FIXME status

    @classmethod
    def get_fallback(cls):
        return cls._meta.get_field('default_locale')

    def __unicode__(self):
        return unicode(self.url or '(no url set)')


models.signals.pre_save.connect(save_signal, sender=Website,
                                dispatch_uid='website_translations')
