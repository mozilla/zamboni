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
from mkt.api.fields import IntegerRangeField
from mkt.constants.applications import DEVICE_TYPES
from mkt.constants.base import LISTED_STATUSES, STATUS_CHOICES, STATUS_NULL
from mkt.site.models import ManagerBase, ModelBase
from mkt.site.utils import get_icon_url
from mkt.tags.models import Tag
from mkt.translations.fields import save_signal, TranslatedField
from mkt.users.models import UserProfile
from mkt.websites.indexers import WebsiteIndexer


DEFAULT_ICON_REGIONS = ['americas', 'asia-australia', 'europe-africa']
DEFAULT_ICON_COLORS = ['blue', 'cerulean', 'green', 'orange', 'pink', 'purple',
                       'red', 'yellow']
DEFAULT_ICONS = ['-'.join([region, color])
                 for region in DEFAULT_ICON_REGIONS
                 for color in DEFAULT_ICON_COLORS]


class WebsiteSubmissionManager(ManagerBase):
    """
    Custom manager for the WebsiteSubmission model. By default, exclude all
    approved sites from querysets.
    """
    def get_queryset(self):
        qs = super(WebsiteSubmissionManager, self).get_queryset()
        return qs.filter(approved=False)

    def approved(self):
        qs = super(WebsiteSubmissionManager, self).get_queryset()
        return qs.filter(approved=True)


class WebsiteSubmission(ModelBase):
    """
    Model representing a website submission.

    When approved, the data from this will be copied to a new instance of the
    Website model, and approved=True will be set on the submission instance.
    """
    name = TranslatedField()
    keywords = models.ManyToManyField(Tag)
    description = TranslatedField()
    categories = JSONField(default=None)

    date_approved = models.DateTimeField(blank=True)

    # `detected_icon` is the URL of the icon we are able to gather from the
    # submitted site's metadata. In the reviewer tools, reviewers will be able
    # to accept that icon, or upload one of their own.
    detected_icon = models.URLField(max_length=255, blank=True)
    icon_type = models.CharField(max_length=25, blank=True)
    icon_hash = models.CharField(max_length=8, blank=True)

    # The `url` field is the URL as entered by the submitter. The
    # `canonical_url` field is the URL that the site reports as the canonical
    # location for the submitted URL. In the reviewer tools, reviewers will
    # have the ability to copy the `canonical_url` value to the `url` field.
    url = models.URLField(max_length=255)
    canonical_url = models.URLField(max_length=255, blank=True, null=True)

    # A 1-5 Likert scale indicating how well the submitter says the website
    # works. This is primarily used to make the submitter question the
    # relevance of their submission, though submissions should be prevented if
    # the user says it works poorly.
    works_well = IntegerRangeField(min_value=2, max_value=5)

    # Who is submitting the website? Do they want public credit for their
    # submission?
    submitter = models.ForeignKey(UserProfile,
                                  related_name='websites_submitted')
    public_credit = models.BooleanField(default=False)

    # Why does the user think the website is relevant to Marketplace?
    why_relevant = models.TextField()

    # If the submitter says the website is relevant worldwide,
    # preferred_regions should be set to [].
    preferred_regions = JSONField(default=None)

    # Turn true when a reviewer has approved and published a submission.
    approved = models.BooleanField(default=False, db_index=True)

    objects = WebsiteSubmissionManager()

    class Meta:
        ordering = (('-modified'), )

    def __unicode__(self):
        return unicode(self.url)


WebsiteSubmission._meta.get_field('created').db_index = True
WebsiteSubmission._meta.get_field('modified').db_index = True


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

    # Devices, similar to apps. Stored a JSON list of ids.
    devices = JSONField(default=None)

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
    def device_names(self):
        return [DEVICE_TYPES[device_id].api_name for device_id in self.devices]

    @property
    def device_types(self):
        return [DEVICE_TYPES[device_id] for device_id in self.devices]

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
        icon_name = '{icon}-{{size}}.png'.format(
            icon=DEFAULT_ICONS[self.pk % len(DEFAULT_ICONS)])
        return get_icon_url(static_url('WEBSITE_ICON_URL'), self, size,
                            default_format=icon_name)

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
