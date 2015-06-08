# -*- coding: utf-8 -*-
import operator
import os.path

from django.conf import settings
from django.core.urlresolvers import reverse
from django.db import models
from django.dispatch import receiver

from django_extensions.db.fields.json import JSONField

import mkt
from lib.utils import static_url
from mkt.constants.applications import DEVICE_TYPE_LIST
from mkt.constants.base import LISTED_STATUSES, STATUS_CHOICES, STATUS_NULL
from mkt.site.models import ManagerBase, ModelBase
from mkt.site.utils import get_icon_url
from mkt.tags.models import Tag
from mkt.translations.fields import save_signal, TranslatedField
from mkt.websites.indexers import WebsiteIndexer


class WebsiteManager(ManagerBase):
    def valid(self):
        return self.filter(status__in=LISTED_STATUSES, is_disabled=False)


class Website(ModelBase):
    # Identifier used for the initial e.me import.
    moz_id = models.PositiveIntegerField(null=True, unique=True, blank=True)

    # The default_locale used for translated fields. See get_fallback() method
    # below.
    default_locale = models.CharField(max_length=10,
                                      default=settings.LANGUAGE_CODE)
    # The Website URL.
    url = models.URLField(max_length=255, blank=True, null=True)

    # The Website mobile-specific URL, if one exists.
    mobile_url = models.URLField(max_length=255, blank=True, null=True)

    # The <title> for the Website, used in search, not exposed to the frontend.
    title = TranslatedField()

    # The name and optionnal short name for the Website, used in the detail
    # page and listing pages, respectively.
    name = TranslatedField()
    short_name = TranslatedField()

    # Description.
    description = TranslatedField()

    # Website keywords.
    keywords = models.ManyToManyField(Tag)

    # Regions the website is known to be relevant in, used for search boosting.
    # Stored as a JSON list of ids.
    preferred_regions = JSONField(default=None)

    # Categories, similar to apps. Stored as a JSON list of names.
    categories = JSONField(default=None)

    # Icon content-type.
    icon_type = models.CharField(max_length=25, blank=True)

    # Icon cache-busting hash.
    icon_hash = models.CharField(max_length=8, blank=True)

    # Date & time the entry was last updated.
    last_updated = models.DateTimeField(db_index=True, auto_now_add=True)

    # Status, similar to apps. See WebsiteManager.valid() above.
    status = models.PositiveIntegerField(
        choices=STATUS_CHOICES.items(), default=STATUS_NULL)

    # Whether the website entry is disabled (not shown in frontend, regardless
    # of status) or not.
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
    def devices(self):
        # If the frontend wants to hide websites on desktop, it passes
        # doc_type='webapp' to the search view. Since a dev/device parameter is
        # sent anyway, we want ES to consider websites are compatible with all
        # devices.
        return [device.id for device in DEVICE_TYPE_LIST]

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

    def get_url_path(self):
        return reverse('website.detail', kwargs={'pk': self.pk})

    def get_preferred_regions(self, sort_by='slug'):
        """
        Return a list of region objects the website is preferred in, e.g.::

             [<class 'mkt.constants.regions.GBR'>, ...]

        """
        _regions = map(mkt.regions.REGIONS_CHOICES_ID_DICT.get,
                       self.preferred_regions)
        return sorted(_regions, key=operator.attrgetter(sort_by))


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
