from django.db import models

import amo.models
from amo.decorators import use_master
from amo.models import SlugField
from addons.models import clean_slug

from mkt.webapps.models import Webapp
from mkt.webapps.tasks import index_webapps


class BaseFeedCollectionMembership(amo.models.ModelBase):
    """

    """
    app = models.ForeignKey(Webapp)
    order = models.SmallIntegerField(null=True)
    obj = None

    class Meta:
        abstract = True
        ordering = ('order',)
        unique_together = ('obj', 'app',)


class BaseFeedCollection(amo.models.ModelBase):
    """
    On the feed, there are a number of types of feed items that share a similar
    structure: a slug, one or more apps,

    This is a base class for those feed items, including:

    - Editorial Brands: `FeedBrand`
    - Collections: `FeedCollection`
    - Operator Shelves: `FeedOperatorShelf`

    Subclasses must do  a few things:

    - Define an M2M field named `_apps` with a custom through model that
      inherits from `BaseFeedCollectionMembership`.
    - Set the `membership_class` class property to the custom through model
      used by `_apps`.
    - Set the `membership_relation` class property to the name of the relation
      on the model.
    """
    _apps = None
    slug = SlugField(blank=True, max_length=30,
                     help_text='Used in collection URLs.')

    membership_class = None
    membership_relation = None

    objects = amo.models.ManagerBase()

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
            'status': amo.STATUS_PUBLIC
        }
        return self._apps.filter(**filters).order_by(self.membership_relation)

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

    def reorder(self, new_order):
        """
        Passed a list of app IDs, e.g.

        [18, 24, 9]

        will change the order of each item in the collection to match the
        passed order. A ValueError will be raised if each app in the
        collection is not included in the ditionary.
        """
        existing_pks = self.apps().no_cache().values_list('pk', flat=True)
        if set(existing_pks) != set(new_order):
            raise ValueError('Not all apps included')
        for order, pk in enumerate(new_order):
            member = self.membership_class.objects.get(obj=self, app_id=pk)
            member.update(order=order)
        index_webapps.delay(new_order)
