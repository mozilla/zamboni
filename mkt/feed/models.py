"""
The feed is an assembly of items of different content types.
For ease of querying, each different content type is housed in the FeedItem
model, which also houses metadata indicating the conditions under which it
should be included. So a feed is actually just a listing of FeedItem instances
that match the user's region and carrier.

Current content types able to be attached to FeedItem:
- `FeedApp` (via the `app` field)
- `FeedBrand` (via the `brand` field)
- `FeedCollection` (via the `collection` field)
"""
import os

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver

import mkt
import mkt.carriers
import mkt.regions
from mkt.constants.categories import CATEGORY_CHOICES
from mkt.feed import indexers
from mkt.ratings.validators import validate_rating
from mkt.site.decorators import use_master
from mkt.site.fields import ColorField
from mkt.site.models import ManagerBase, ModelBase
from mkt.translations.fields import PurifiedField, TranslatedField, save_signal
from mkt.webapps.models import clean_slug, Preview, Webapp
from mkt.webapps.tasks import index_webapps

from .constants import (BRAND_LAYOUT_CHOICES, BRAND_TYPE_CHOICES,
                        COLLECTION_TYPE_CHOICES,
                        FEEDAPP_TYPE_CHOICES)


class BaseFeedCollection(ModelBase):
    """
    On the feed, there are a number of types of feed items that share a similar
    structure: a slug, one or more member apps with a maintained sort order,
    and a number of methods and common views for operating on those apps. This
    is a base class for those feed items, including:

    - Editorial Brands: `FeedBrand`
    - Collections: `FeedCollection`
    - Operator Shelves: `FeedShelf`

    A series of base classes wraps the common code for these:

    - BaseFeedCollection
    - BaseFeedCollectionMembership
    - BaseFeedCollectionSerializer
    - BaseFeedCollectionViewSet

    Subclasses of BaseFeedCollection must do a few things:
    - Define an M2M field named `_apps` with a custom through model that
      inherits from `BaseFeedCollectionMembership`.
    - Set the `membership_class` class property to the custom through model
      used by `_apps`.
    - Set the `membership_relation` class property to the name of the relation
      on the model.
    """
    _apps = None
    slug = models.CharField(blank=True, max_length=30, unique=True,
                            help_text='Used in collection URLs.')

    membership_class = None
    membership_relation = None

    objects = ManagerBase()

    class Meta:
        abstract = True
        ordering = ('-id',)

    def save(self, **kw):
        self.clean_slug()
        return super(BaseFeedCollection, self).save(**kw)

    @use_master
    def clean_slug(self):
        clean_slug(self, 'slug')

    def apps(self):
        """
        Public apps on the collection, ordered by their position in the
        CollectionMembership model.

        Use this method everytime you want to display apps for a collection to
        an user.
        """
        filters = {
            'disabled_by_user': False,
            'status': mkt.STATUS_PUBLIC
        }
        return self._apps.order_by(self.membership_relation).filter(**filters)

    def add_app(self, app, order=None):
        """
        Add an app to this collection. If specified, the app will be created
        with the specified `order`. If not, it will be added to the end of the
        collection.
        """
        qs = self.membership_class.objects.filter(obj=self)

        if order is None:
            aggregate = qs.aggregate(models.Max('order'))['order__max']
            order = aggregate + 1 if aggregate is not None else 0

        rval = self.membership_class.objects.create(obj=self, app=app,
                                                    order=order)

        # Help django-cache-machine: it doesn't like many 2 many relations,
        # the cache is never invalidated properly when adding a new object.
        self.membership_class.objects.invalidate(*qs)
        index_webapps.delay([app.pk])
        return rval

    def remove_app(self, app):
        """
        Remove the passed app from this collection, returning a boolean
        indicating whether a successful deletion took place.
        """
        try:
            membership = self.membership_class.objects.get(obj=self, app=app)
        except self.membership_class.DoesNotExist:
            return False
        else:
            membership.delete()
            index_webapps.delay([app.pk])
            return True

    def remove_apps(self):
        """Remove all apps from collection."""
        self.membership_class.objects.filter(obj=self).delete()

    def set_apps(self, new_apps):
        """
        Passed a list of app IDs, will remove all existing members on the
        collection and create new ones for each of the passed apps, in order.
        """
        self.remove_apps()
        for app_id in new_apps:
            self.add_app(Webapp.objects.get(pk=app_id))
        index_webapps.delay(new_apps)


class BaseFeedImage(models.Model):
    image_hash = models.CharField(default=None, max_length=8, null=True,
                                  blank=True)

    class Meta:
        abstract = True


class GroupedAppsMixin(object):
    """
    An app's membership to a `FeedShelf` class, used as the through model for
    `FeedShelf._apps`.
    """
    def add_app_grouped(self, app, group, order=None):
        """
        Add an app to this collection, as a member of the passed `group`.

        If specified, the app will be created with the specified `order`. If
        not, it will be added to the end of the collection.
        """
        qs = self.membership_class.objects.filter(obj=self)
        if order is None:
            aggregate = qs.aggregate(models.Max('order'))['order__max']
            order = aggregate + 1 if aggregate is not None else 0

        rval = self.membership_class.objects.create(obj_id=self.id, app_id=app,
                                                    group=group, order=order)

        # Help django-cache-machine: it doesn't like many 2 many relations,
        # the cache is never invalidated properly when adding a new object.
        self.membership_class.objects.invalidate(*qs)
        index_webapps.delay([app])
        return rval

    def set_apps_grouped(self, new_apps):
        self.remove_apps()
        for group in new_apps:
            for app in group['apps']:
                self.add_app_grouped(app, group['name'])


class BaseFeedCollectionMembership(ModelBase):
    """
    A custom `through` model is required for the M2M field `_apps` on
    subclasses of `BaseFeedCollection`. This model houses an `order` field that
    maintains the order of apps in the collection. This model serves as an
    abstract base class for the custom `through` models.

    Subclasses must:
    - Define a `ForeignKey` named `obj` that relates the app to the instance
      being put on the feed.
    """
    app = models.ForeignKey(Webapp)
    order = models.SmallIntegerField(null=True)
    obj = None

    class Meta:
        abstract = True
        ordering = ('order',)
        unique_together = ('obj', 'app',)


class FeedBrandMembership(BaseFeedCollectionMembership):
    """
    An app's membership to a `FeedBrand` class, used as the through model for
    `FeedBrand._apps`.
    """
    obj = models.ForeignKey('FeedBrand')

    class Meta(BaseFeedCollectionMembership.Meta):
        abstract = False
        db_table = 'mkt_feed_brand_membership'


class FeedBrand(BaseFeedCollection):
    """
    Model for "Editorial Brands", a special type of collection that allows
    editors to quickly create content without involving localizers by choosing
    from one of a number of predefined, prelocalized titles.
    """
    _apps = models.ManyToManyField(Webapp, through=FeedBrandMembership,
                                   related_name='app_feed_brands')
    layout = models.CharField(choices=BRAND_LAYOUT_CHOICES, max_length=30)
    type = models.CharField(choices=BRAND_TYPE_CHOICES, max_length=30)

    membership_class = FeedBrandMembership
    membership_relation = 'feedbrandmembership'

    class Meta(BaseFeedCollection.Meta):
        abstract = False
        db_table = 'mkt_feed_brand'

    @classmethod
    def get_indexer(self):
        return indexers.FeedBrandIndexer


class FeedCollectionMembership(BaseFeedCollectionMembership):
    """
    An app's membership to a `FeedCollection` class, used as the through model
    for `FeedBrand._apps`.
    """
    obj = models.ForeignKey('FeedCollection')
    group = PurifiedField(blank=True, null=True)

    class Meta(BaseFeedCollectionMembership.Meta):
        abstract = False
        db_table = 'mkt_feed_collection_membership'


class FeedCollection(GroupedAppsMixin, BaseFeedCollection,
                     BaseFeedImage):
    """
    Model for "Collections", a type of curated collection that allows more
    complex grouping of apps than an Editorial Brand.
    """
    _apps = models.ManyToManyField(Webapp, through=FeedCollectionMembership,
                                   related_name='app_feed_collections')
    color = models.CharField(max_length=20, null=True, blank=True)
    name = TranslatedField()
    description = PurifiedField(blank=True, null=True)
    type = models.CharField(choices=COLLECTION_TYPE_CHOICES, max_length=30,
                            null=True)

    # Deprecated.
    background_color = models.CharField(max_length=7, null=True, blank=True)

    membership_class = FeedCollectionMembership
    membership_relation = 'feedcollectionmembership'

    class Meta(BaseFeedCollection.Meta):
        abstract = False
        db_table = 'mkt_feed_collection'

    @classmethod
    def get_indexer(self):
        return indexers.FeedCollectionIndexer

    def image_path(self, suffix=''):
        return os.path.join(settings.FEED_COLLECTION_BG_PATH,
                            str(self.pk / 1000),
                            'feed_collection{suffix}_{pk}.png'.format(
                                suffix=suffix, pk=self.pk))


class FeedShelfMembership(BaseFeedCollectionMembership):
    """
    An app's membership to a `FeedShelf` class, used as the through model for
    `FeedShelf._apps`.
    """
    group = PurifiedField(blank=True, null=True)
    obj = models.ForeignKey('FeedShelf')

    class Meta(BaseFeedCollectionMembership.Meta):
        abstract = False
        db_table = 'mkt_feed_shelf_membership'


class FeedShelf(GroupedAppsMixin, BaseFeedCollection, BaseFeedImage):
    """
    Model for "Operator Shelves", a special type of collection that gives
    operators a place to centralize content they wish to feature.
    """
    _apps = models.ManyToManyField(Webapp, through=FeedShelfMembership,
                                   related_name='app_shelves')
    carrier = models.IntegerField(choices=mkt.carriers.CARRIER_CHOICES)
    description = PurifiedField(null=True)
    name = TranslatedField()
    region = models.PositiveIntegerField(
        choices=mkt.regions.REGIONS_CHOICES_ID)

    # Shelf landing image.
    image_landing_hash = models.CharField(default=None, max_length=8,
                                          null=True, blank=True)

    membership_class = FeedShelfMembership
    membership_relation = 'feedshelfmembership'

    class Meta(BaseFeedCollection.Meta):
        abstract = False
        db_table = 'mkt_feed_shelf'

    @classmethod
    def get_indexer(self):
        return indexers.FeedShelfIndexer

    def image_path(self, suffix=''):
        return os.path.join(settings.FEED_SHELF_BG_PATH,
                            str(self.pk / 1000),
                            'feed_shelf{suffix}_{pk}.png'.format(
                                suffix=suffix, pk=self.pk))

    @property
    def is_published(self):
        return self.feeditem_set.exists()


class FeedApp(BaseFeedImage, ModelBase):
    """
    Model for "Custom Featured Apps", a feed item highlighting a single app
    and some additional metadata (e.g. a review or a screenshot).
    """
    app = models.ForeignKey(Webapp)
    description = PurifiedField()
    slug = models.CharField(max_length=30, unique=True)
    color = models.CharField(max_length=20, null=True, blank=True)
    type = models.CharField(choices=FEEDAPP_TYPE_CHOICES, max_length=30)

    # Optionally linked to a Preview (screenshot or video).
    preview = models.ForeignKey(Preview, null=True, blank=True)

    # Optionally linked to a pull quote.
    pullquote_attribution = models.CharField(max_length=50, null=True,
                                             blank=True)
    pullquote_rating = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[validate_rating])
    pullquote_text = PurifiedField(null=True)

    # Deprecated.
    background_color = ColorField(null=True)

    class Meta:
        db_table = 'mkt_feed_app'

    @classmethod
    def get_indexer(self):
        return indexers.FeedAppIndexer

    def clean(self):
        """
        Require `pullquote_text` if `pullquote_rating` or
        `pullquote_attribution` are set.
        """
        if not self.pullquote_text and (self.pullquote_rating or
                                        self.pullquote_attribution):
            raise ValidationError('Pullquote text required if rating or '
                                  'attribution is defined.')
        super(FeedApp, self).clean()

    def image_path(self, suffix=''):
        return os.path.join(settings.FEATURED_APP_BG_PATH,
                            str(self.pk / 1000),
                            'featured_app{suffix}_{pk}.png'.format(
                                suffix=suffix, pk=self.pk))


class FeedItem(ModelBase):
    """
    A thin wrapper for all items that live on the feed, including metadata
    describing the conditions that the feed item should be included in a user's
    feed.
    """
    category = models.CharField(null=True, blank=True, max_length=30,
                                choices=CATEGORY_CHOICES)
    region = models.PositiveIntegerField(
        default=None, null=True, blank=True, db_index=True,
        choices=mkt.regions.REGIONS_CHOICES_ID)
    carrier = models.IntegerField(default=None, null=True, blank=True,
                                  choices=mkt.carriers.CARRIER_CHOICES,
                                  db_index=True)
    order = models.SmallIntegerField(null=True)
    item_type = models.CharField(max_length=30)

    # Types of objects that may be contained by a feed item.
    app = models.ForeignKey(FeedApp, blank=True, null=True)
    brand = models.ForeignKey(FeedBrand, blank=True, null=True)
    collection = models.ForeignKey(FeedCollection, blank=True, null=True)
    shelf = models.ForeignKey(FeedShelf, blank=True, null=True)

    class Meta:
        db_table = 'mkt_feed_item'
        ordering = ('order',)

    @classmethod
    def get_indexer(cls):
        return indexers.FeedItemIndexer


# Maintain ElasticSearch index.
@receiver(models.signals.post_save, sender=FeedApp,
          dispatch_uid='feedapp.search.index')
@receiver(models.signals.post_save, sender=FeedBrand,
          dispatch_uid='feedbrand.search.index')
@receiver(models.signals.post_save, sender=FeedCollection,
          dispatch_uid='feedcollection.search.index')
@receiver(models.signals.post_save, sender=FeedShelf,
          dispatch_uid='feedshelf.search.index')
@receiver(models.signals.post_save, sender=FeedItem,
          dispatch_uid='feeditem.search.index')
def update_search_index(sender, instance, **kw):
    instance.get_indexer().index_ids([instance.id])


# Delete ElasticSearch index on delete.
@receiver(models.signals.post_delete, sender=FeedApp,
          dispatch_uid='feedapp.search.unindex')
@receiver(models.signals.post_delete, sender=FeedBrand,
          dispatch_uid='feedbrand.search.unindex')
@receiver(models.signals.post_delete, sender=FeedCollection,
          dispatch_uid='feedcollection.search.unindex')
@receiver(models.signals.post_delete, sender=FeedShelf,
          dispatch_uid='feedshelf.search.unindex')
@receiver(models.signals.post_delete, sender=FeedItem,
          dispatch_uid='feeditem.search.unindex')
def delete_search_index(sender, instance, **kw):
    instance.get_indexer().unindex(instance.id)


# Save translations when saving instance with translated fields.
models.signals.pre_save.connect(
    save_signal, sender=FeedApp,
    dispatch_uid='feedapp_translations')
models.signals.pre_save.connect(
    save_signal, sender=FeedCollection,
    dispatch_uid='feedcollection_translations')
models.signals.pre_save.connect(
    save_signal, sender=FeedCollectionMembership,
    dispatch_uid='feedcollectionmembership_translations')
models.signals.pre_save.connect(
    save_signal, sender=FeedShelf,
    dispatch_uid='feedshelf_translations')
models.signals.pre_save.connect(
    save_signal, sender=FeedShelfMembership,
    dispatch_uid='feedshelfmembership_translations')


# Delete membership instances when their apps are deleted.
def remove_memberships(*args, **kwargs):
    instance = kwargs.get('instance')
    for cls in [FeedBrandMembership, FeedCollectionMembership,
                FeedShelfMembership]:
        cls.objects.filter(app_id=instance.pk).delete()

post_delete.connect(remove_memberships, sender=Webapp, weak=False,
                    dispatch_uid='cleanup_feed_membership')
