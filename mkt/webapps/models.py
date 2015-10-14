# -*- coding: utf-8 -*-
import datetime
import hashlib
import itertools
import json
import operator
import os
import time
import urlparse
import uuid

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.db import models, transaction
from django.db.models import signals as dbsignals, Max, Q
from django.dispatch import receiver
from django.utils.translation import trans_real as translation

import commonware.log
from cache_nuggets.lib import memoize, memoize_key
from django_extensions.db.fields.json import JSONField
from jingo.helpers import urlparams
from jinja2.filters import do_dictsort
from tower import ugettext as _
from tower import ugettext_lazy as _lazy

import mkt
from lib.crypto import packaged
from lib.iarc.client import get_iarc_client
from lib.iarc.utils import get_iarc_app_title, render_xml
from lib.utils import static_url
from mkt.access import acl
from mkt.constants import APP_FEATURES, apps, iarc_mappings
from mkt.constants.applications import DEVICE_TYPES
from mkt.constants.payments import PROVIDER_CHOICES
from mkt.constants.regions import RESTOFWORLD
from mkt.files.models import File, nfd_str
from mkt.files.utils import parse_addon, WebAppParser
from mkt.prices.models import AddonPremium
from mkt.ratings.models import Review
from mkt.regions.utils import parse_region
from mkt.site.decorators import use_master
from mkt.site.helpers import absolutify
from mkt.site.mail import send_mail
from mkt.site.models import (DynamicBoolFieldsMixin, ManagerBase, ModelBase,
                             OnChangeMixin)
from mkt.site.storage_utils import (copy_stored_file, local_storage,
                                    private_storage, public_storage,
                                    storage_is_remote)
from mkt.site.utils import (cached_property, get_icon_url, get_promo_img_url,
                            slugify, smart_path, sorted_groupby)
from mkt.tags.models import Tag
from mkt.translations.fields import (PurifiedField, save_signal,
                                     TranslatedField, Translation)
from mkt.translations.models import attach_trans_dict
from mkt.translations.utils import find_language, to_language
from mkt.users.models import UserForeignKey, UserProfile
from mkt.versions.models import Version
from mkt.webapps import signals
from mkt.webapps.indexers import WebappIndexer
from mkt.webapps.utils import (dehydrate_content_rating, get_locale_properties,
                               get_cached_minifest, get_supported_locales)


log = commonware.log.getLogger('z.addons')


def clean_slug(instance, slug_field='app_slug'):
    """Cleans a model instance slug.

    This strives to be as generic as possible as it's used by Webapps
    and maybe less in the future. :-D

    """
    slug = getattr(instance, slug_field, None) or instance.name

    if not slug:
        # Initialize the slug with what we have available: a name translation,
        # or the id of the instance, or in last resort the model name.
        translations = Translation.objects.filter(id=instance.name_id)
        if translations.exists():
            slug = translations[0]
        elif instance.id:
            slug = str(instance.id)
        else:
            slug = instance.__class__.__name__

    max_length = instance._meta.get_field_by_name(slug_field)[0].max_length
    slug = slugify(slug)[:max_length]

    if BlockedSlug.blocked(slug):
        slug = slug[:max_length - 1] + '~'

    # The following trick makes sure we are using a manager that returns
    # all the objects, as otherwise we could have a slug clash on our hands.
    # Eg with the "Addon.objects" manager, which doesn't list deleted addons,
    # we could have a "clean" slug which is in fact already assigned to an
    # already existing (deleted) addon.
    # Also, make sure we use the base class (eg Webapp, which inherits from
    # Addon, shouldn't clash with addons). This is extra paranoid, as webapps
    # have a different slug field, but just in case we need this in the future.
    manager = models.Manager()
    manager.model = instance._meta.proxy_for_model or instance.__class__

    qs = manager.values_list(slug_field, flat=True)  # Get list of all slugs.
    if instance.id:
        qs = qs.exclude(pk=instance.id)  # Can't clash with itself.

    # We first need to make sure there's a clash, before trying to find a
    # suffix that is available. Eg, if there's a "foo-bar" slug, "foo" is still
    # available.
    clash = qs.filter(**{slug_field: slug})
    if clash.exists():
        # Leave space for "-" and 99 clashes.
        slug = slugify(slug)[:max_length - 3]

        # There is a clash, so find a suffix that will make this slug unique.
        prefix = '%s-' % slug
        lookup = {'%s__startswith' % slug_field: prefix}
        clashes = qs.filter(**lookup)

        # Try numbers between 1 and the number of clashes + 1 (+ 1 because we
        # start the range at 1, not 0):
        # if we have two clashes "foo-1" and "foo-2", we need to try "foo-x"
        # for x between 1 and 3 to be absolutely sure to find an available one.
        for idx in range(1, len(clashes) + 2):
            new = ('%s%s' % (prefix, idx))[:max_length]
            if new not in clashes:
                slug = new
                break
        else:
            # This could happen. The current implementation (using
            # ``[:max_length -3]``) only works for the first 100 clashes in the
            # worst case (if the slug is equal to or longuer than
            # ``max_length - 3`` chars).
            # After that, {verylongslug}-100 will be trimmed down to
            # {verylongslug}-10, which is already assigned, but it's the last
            # solution tested.
            raise RuntimeError

    setattr(instance, slug_field, slug)

    return instance


class AddonDeviceType(ModelBase):
    addon = models.ForeignKey('Webapp')
    device_type = models.PositiveIntegerField(
        default=mkt.DEVICE_DESKTOP.id, choices=do_dictsort(mkt.DEVICE_TYPES))

    class Meta:
        db_table = 'addons_devicetypes'
        unique_together = ('addon', 'device_type')

    def __unicode__(self):
        return u'%s: %s' % (self.addon.name, self.device.name)

    @property
    def device(self):
        return mkt.DEVICE_TYPES[self.device_type]


@receiver(signals.version_changed, dispatch_uid='version_changed')
def version_changed(sender, **kw):
    from . import tasks
    tasks.version_changed.delay(sender.id)


def attach_devices(addons):
    addon_dict = dict((a.id, a) for a in addons)
    devices = (AddonDeviceType.objects.filter(addon__in=addon_dict)
               .values_list('addon', 'device_type'))
    for addon, device_types in sorted_groupby(devices, lambda x: x[0]):
        addon_dict[addon].device_ids = [d[1] for d in device_types]


def attach_prices(addons):
    addon_dict = dict((a.id, a) for a in addons)
    prices = (AddonPremium.objects
              .filter(addon__in=addon_dict,
                      addon__premium_type__in=mkt.ADDON_PREMIUMS)
              .values_list('addon', 'price__price'))
    for addon, price in prices:
        addon_dict[addon].price = price


def attach_translations(addons):
    """Put all translations into a translations dict."""
    attach_trans_dict(Webapp, addons)


class AddonUser(models.Model):
    addon = models.ForeignKey('Webapp')
    user = UserForeignKey()
    role = models.PositiveSmallIntegerField(default=mkt.AUTHOR_ROLE_OWNER,
                                            choices=mkt.AUTHOR_CHOICES)
    listed = models.BooleanField(_lazy(u'Listed'), default=True)
    position = models.IntegerField(default=0)

    def __init__(self, *args, **kwargs):
        super(AddonUser, self).__init__(*args, **kwargs)
        self._original_role = self.role
        self._original_user_id = self.user_id

    class Meta:
        db_table = 'addons_users'
        unique_together = ('addon', 'user')
        index_together = (('addon', 'user', 'listed'),
                          ('addon', 'listed'))


class Preview(ModelBase):
    addon = models.ForeignKey('Webapp', related_name='previews')
    filetype = models.CharField(max_length=25)
    thumbtype = models.CharField(max_length=25)
    caption = TranslatedField()

    position = models.IntegerField(default=0)
    sizes = JSONField(max_length=25)

    class Meta:
        db_table = 'previews'
        ordering = ('position', 'created')
        index_together = ('addon', 'position', 'created')

    def _image_url(self, is_thumbnail=False):
        if self.modified is not None:
            if isinstance(self.modified, unicode):
                self.modified = datetime.datetime.strptime(self.modified,
                                                           '%Y-%m-%dT%H:%M:%S')
            modified = int(time.mktime(self.modified.timetuple()))
        else:
            modified = 0
        if storage_is_remote():
            path = self._image_path(is_thumbnail=is_thumbnail)
            return '%s?modified=%s' % (public_storage.url(path), modified)
        else:
            if is_thumbnail:
                url_template = static_url('PREVIEW_THUMBNAIL_URL')
            else:
                url_template = static_url('PREVIEW_FULL_URL')
            args = [self.id / 1000, self.id, modified]
            if '.png' not in url_template:
                args.insert(2, self.file_extension)
            return url_template % tuple(args)

    def _image_path(self, is_thumbnail=False):
        if is_thumbnail:
            path_template = settings.PREVIEW_THUMBNAIL_PATH
        else:
            path_template = settings.PREVIEW_FULL_PATH
        args = [self.id / 1000, self.id]
        if '.png' not in path_template:
            args.append(self.file_extension)
        return path_template % tuple(args)

    def as_dict(self, src=None):
        d = {'full': urlparams(self.image_url, src=src),
             'thumbnail': urlparams(self.thumbnail_url, src=src),
             'caption': unicode(self.caption)}
        return d

    @property
    def is_landscape(self):
        size = self.image_size
        if not size:
            return False
        return size[0] > size[1]

    @property
    def file_extension(self):
        # Assume that blank is an image.
        if not self.filetype:
            return 'png'
        return self.filetype.split('/')[1]

    @property
    def thumbnail_url(self):
        return self._image_url(is_thumbnail=True)

    @property
    def image_url(self):
        return self._image_url()

    @property
    def thumbnail_path(self):
        return self._image_path(is_thumbnail=True)

    @property
    def image_path(self):
        return self._image_path()

    @property
    def thumbnail_size(self):
        return self.sizes.get('thumbnail', []) if self.sizes else []

    @property
    def image_size(self):
        return self.sizes.get('image', []) if self.sizes else []


dbsignals.pre_save.connect(save_signal, sender=Preview,
                           dispatch_uid='preview_translations')


class BlockedSlug(ModelBase):
    name = models.CharField(max_length=255, unique=True, default='')

    class Meta:
        db_table = 'addons_blocked_slug'

    def __unicode__(self):
        return self.name

    @classmethod
    def blocked(cls, slug):
        return slug.isdigit() or cls.objects.filter(name=slug).exists()


def reverse_version(version):
    """
    The try/except AttributeError allows this to be used where the input is
    ambiguous, and could be either an already-reversed URL or a Version object.
    """
    if version:
        try:
            return reverse('version-detail', kwargs={'pk': version.pk})
        except AttributeError:
            return version
    return


class WebappManager(ManagerBase):

    def __init__(self, include_deleted=False):
        ManagerBase.__init__(self)
        self.include_deleted = include_deleted

    def get_queryset(self):
        qs = super(WebappManager, self).get_queryset()
        if not self.include_deleted:
            qs = qs.exclude(status=mkt.STATUS_DELETED)
        return qs.transform(Webapp.transformer)

    def valid(self):
        return self.filter(status__in=mkt.LISTED_STATUSES,
                           disabled_by_user=False)

    def visible(self):
        return self.filter(status__in=mkt.LISTED_STATUSES,
                           disabled_by_user=False)

    def pending_in_region(self, region):
        """
        Apps that have been approved by reviewers but unapproved by
        reviewers in special regions (e.g., China).

        """
        region = parse_region(region)
        column_prefix = '_geodata__region_%s' % region.slug
        return self.filter(**{
            # Only nominated apps should show up.
            '%s_nominated__isnull' % column_prefix: False,
            'status__in': mkt.WEBAPPS_APPROVED_STATUSES,
            'disabled_by_user': False,
            'escalationqueue__isnull': True,
            '%s_status' % column_prefix: mkt.STATUS_PENDING,
        }).order_by('-%s_nominated' % column_prefix)

    def rated(self):
        """IARC."""
        return self.exclude(content_ratings__isnull=True)

    def by_identifier(self, identifier):
        """
        Look up a single app by its `id` or `app_slug`.

        If the identifier is coercable into an integer, we first check for an
        ID match, falling back to a slug check (probably not necessary, as
        there is validation preventing numeric slugs). Otherwise, we only look
        for a slug match.
        """
        try:
            return self.get(id=identifier)
        except (ObjectDoesNotExist, ValueError):
            return self.get(app_slug=identifier)


class UUIDModelMixin(object):
    """
    A mixin responsible for assigning a uniquely generated
    UUID at save time.
    """

    def save(self, *args, **kwargs):
        self.assign_uuid()
        return super(UUIDModelMixin, self).save(*args, **kwargs)

    def assign_uuid(self):
        """Generates a UUID if self.guid is not already set."""
        if not hasattr(self, 'guid'):
            raise AttributeError(
                'A UUIDModel must contain a charfield called guid')

        if not self.guid:
            max_tries = 10
            tried = 1
            guid = str(uuid.uuid4())
            while tried <= max_tries:
                if not type(self).objects.filter(guid=guid).exists():
                    self.guid = guid
                    break
                else:
                    guid = str(uuid.uuid4())
                    tried += 1
            else:
                raise ValueError('Could not auto-generate a unique UUID')


class Webapp(UUIDModelMixin, OnChangeMixin, ModelBase):

    STATUS_CHOICES = mkt.STATUS_CHOICES.items()

    guid = models.CharField(max_length=255, unique=True, null=True)
    app_slug = models.CharField(max_length=30, unique=True, null=True,
                                blank=True)
    name = TranslatedField(default=None)
    default_locale = models.CharField(max_length=10,
                                      default=settings.LANGUAGE_CODE,
                                      db_column='defaultlocale')
    status = models.PositiveSmallIntegerField(
        choices=STATUS_CHOICES, db_index=True, default=0)
    highest_status = models.PositiveSmallIntegerField(
        choices=STATUS_CHOICES, default=0,
        help_text='An upper limit for what an author can change.',
        db_column='higheststatus')
    icon_type = models.CharField(max_length=25, blank=True,
                                 db_column='icontype')
    icon_hash = models.CharField(max_length=8, blank=True, null=True)
    promo_img_hash = models.CharField(max_length=8, blank=True, null=True)
    homepage = TranslatedField()
    support_email = TranslatedField(db_column='supportemail')
    support_url = TranslatedField(db_column='supporturl')
    description = PurifiedField(short=False)
    privacy_policy = PurifiedField(db_column='privacypolicy')
    average_rating = models.FloatField(default=0, db_column='averagerating')
    bayesian_rating = models.FloatField(default=0, db_column='bayesianrating',
                                        db_index=True)
    total_reviews = models.PositiveIntegerField(default=0,
                                                db_column='totalreviews')
    last_updated = models.DateTimeField(
        db_index=True, null=True,
        help_text='Last time this add-on had a file/version update')
    disabled_by_user = models.BooleanField(default=False, db_index=True,
                                           db_column='inactive')
    public_stats = models.BooleanField(default=False, db_column='publicstats')
    authors = models.ManyToManyField('users.UserProfile', through='AddonUser',
                                     related_name='addons')
    categories = JSONField(default=None)
    premium_type = models.PositiveSmallIntegerField(
        choices=mkt.ADDON_PREMIUM_TYPES.items(), default=mkt.ADDON_FREE)
    manifest_url = models.URLField(max_length=255, blank=True, null=True)
    app_domain = models.CharField(max_length=255, blank=True, null=True,
                                  db_index=True)
    _current_version = models.ForeignKey(Version, db_column='current_version',
                                         related_name='+', null=True,
                                         on_delete=models.SET_NULL)
    _latest_version = models.ForeignKey(Version, db_column='latest_version',
                                        on_delete=models.SET_NULL,
                                        null=True, related_name='+')
    publish_type = models.PositiveSmallIntegerField(default=0)
    mozilla_contact = models.EmailField(blank=True)
    vip_app = models.BooleanField(default=False)
    priority_review = models.BooleanField(default=False)
    # Whether the app is packaged or not (aka hosted).
    is_packaged = models.BooleanField(default=False, db_index=True)
    enable_new_regions = models.BooleanField(default=True, db_index=True)
    # Annotates disabled apps from the Great IARC purge for auto-reapprove.
    # Note: for currently PUBLIC apps only.
    iarc_purged = models.BooleanField(default=False)
    # This is the public_id to a Generic Solitude Product
    solitude_public_id = models.CharField(max_length=255, null=True,
                                          blank=True)
    is_offline = models.BooleanField(default=False)
    tags = models.ManyToManyField(Tag)

    # Initially, for desktop games.
    hosted_url = models.URLField(max_length=255, blank=True, null=True)

    objects = WebappManager()
    with_deleted = WebappManager(include_deleted=True)

    class PayAccountDoesNotExist(Exception):
        """The app has no payment account for the query."""

    class Meta:
        db_table = 'addons'

    def __unicode__(self):
        return u'%s: %s' % (self.id, self.name)

    def save(self, **kw):
        self.clean_slug()
        creating = not self.id
        super(Webapp, self).save(**kw)
        if creating:
            # Create Geodata object (a 1-to-1 relationship).
            if not hasattr(self, '_geodata'):
                Geodata.objects.create(addon=self)

    @transaction.atomic
    def delete(self, msg='', reason=''):
        # To avoid a circular import.
        from . import tasks

        if self.status == mkt.STATUS_DELETED:
            return  # We're already done.

        id = self.id

        # Tell IARC this app is delisted from the set_iarc_storefront_data.
        tasks.set_storefront_data.delay(self.pk, disable=True)

        # Fetch previews before deleting the addon instance, so that we can
        # pass the list of files to delete to the delete_preview_files task
        # after the addon is deleted.
        previews = list(Preview.objects.filter(addon__id=id)
                        .values_list('id', flat=True))

        log.debug('Deleting app: %s' % self.id)

        to = [settings.APP_DELETION_EMAIL]
        user = mkt.get_user()

        context = {
            'atype': 'App',
            'authors': [u.email for u in self.authors.all()],
            'guid': self.guid,
            'id': self.id,
            'msg': msg,
            'reason': reason,
            'name': self.name,
            'app_slug': self.app_slug,
            'url': absolutify(self.get_url_path()),
            'user_str': ("%s, %s (%s)" % (user.name, user.email, user.id)
                         if user else "Unknown"),
        }

        email_msg = u"""
        The following %(atype)s was deleted.
        %(atype)s: %(name)s
        URL: %(url)s
        DELETED BY: %(user_str)s
        ID: %(id)s
        GUID: %(guid)s
        AUTHORS: %(authors)s
        NOTES: %(msg)s
        REASON GIVEN BY USER FOR DELETION: %(reason)s
        """ % context
        log.debug('Sending delete email for %(atype)s %(id)s' % context)
        subject = 'Deleting %(atype)s %(app_slug)s (%(id)d)' % context

        # Update or NULL out various fields.
        models.signals.pre_delete.send(sender=Webapp, instance=self)
        self.update(status=mkt.STATUS_DELETED, app_slug=str(self.id),
                    app_domain=None, _current_version=None)
        models.signals.post_delete.send(sender=Webapp, instance=self)

        send_mail(subject, email_msg, recipient_list=to)

        for preview in previews:
            tasks.delete_preview_files.delay(preview)

        return True

    def undelete(self):
        # We need to bypass the regular save(), which doesn't like the fact
        # that our base manager filters out deleted objects. We still want
        # signals to happen though, so re-save() once the instance is no longer
        # in deleted state.
        cls = self.__class__
        cls.with_deleted.filter(pk=self.pk).update(status=self.highest_status)
        self.reload()
        self.save()

    @use_master
    def clean_slug(self):
        if self.status == mkt.STATUS_DELETED:
            return
        clean_slug(self, slug_field='app_slug')

    @staticmethod
    def attach_related_versions(addons, addon_dict=None):
        if addon_dict is None:
            addon_dict = dict((a.id, a) for a in addons)

        current_ids = filter(None, (a._current_version_id for a in addons))
        latest_ids = filter(None, (a._latest_version_id for a in addons))
        all_ids = set(current_ids) | set(latest_ids)

        versions = list(Version.objects.filter(id__in=all_ids).order_by())
        for version in versions:
            try:
                addon = addon_dict[version.addon_id]
            except KeyError:
                log.debug('Version %s has an invalid add-on id.' % version.id)
                continue
            if addon._current_version_id == version.id:
                addon._current_version = version
            if addon._latest_version_id == version.id:
                addon._latest_version = version

            version.addon = addon

    @classmethod
    def get_indexer(cls):
        return WebappIndexer

    @classmethod
    def from_upload(cls, upload, is_packaged=False):
        data = parse_addon(upload)
        fields = cls._meta.get_all_field_names()
        addon = Webapp(**dict((k, v) for k, v in data.items() if k in fields))
        addon.status = mkt.STATUS_NULL
        locale_is_set = (addon.default_locale and
                         addon.default_locale in (
                             settings.AMO_LANGUAGES) and
                         data.get('default_locale') == addon.default_locale)
        if not locale_is_set:
            addon.default_locale = to_language(translation.get_language())
        addon.is_packaged = is_packaged
        if is_packaged:
            addon.app_domain = data.get('origin')
        else:
            addon.manifest_url = upload.name
            addon.app_domain = addon.domain_from_url(addon.manifest_url)
        addon.save()
        if data.get('role') == 'homescreen':
            Tag(tag_text='homescreen').save_tag(addon)
        Version.from_upload(upload, addon)

        mkt.log(mkt.LOG.CREATE_ADDON, addon)
        log.debug('New addon %r from %r' % (addon, upload))

        return addon

    @staticmethod
    def attach_previews(addons, addon_dict=None, no_transforms=False):
        if addon_dict is None:
            addon_dict = dict((a.id, a) for a in addons)

        qs = Preview.objects.filter(addon__in=addons,
                                    position__gte=0).order_by()
        if no_transforms:
            qs = qs.no_transforms()
        qs = sorted(qs, key=lambda x: (x.addon_id, x.position, x.created))
        for addon, previews in itertools.groupby(qs, lambda x: x.addon_id):
            addon_dict[addon].all_previews = list(previews)
        # FIXME: set all_previews to empty list on addons without previews.

    @staticmethod
    def attach_premiums(addons, addon_dict=None):
        if addon_dict is None:
            addon_dict = dict((a.id, a) for a in addons)

        # Attach premium addons.
        qs = (AddonPremium.objects.select_related('price')
                                  .filter(addon__in=addons))

        premium_dict = dict((ap.addon_id, ap) for ap in qs)

        # Attach premiums to addons, making sure to attach None to free addons
        # or addons where the corresponding AddonPremium is missing.
        for addon in addons:
            if addon.is_premium():
                addon_p = premium_dict.get(addon.id)
                if addon_p:
                    addon_p.addon = addon
                addon._premium = addon_p
            else:
                addon._premium = None

    def is_public(self):
        """
        True if the app is not disabled and the status is either STATUS_PUBLIC
        or STATUS_UNLISTED.

        Both statuses are "public" in that they should result in a 200 to the
        app detail page.

        """
        return (not self.disabled_by_user and
                self.status in (mkt.STATUS_PUBLIC, mkt.STATUS_UNLISTED))

    def is_approved(self):
        """
        True if the app has status equal to mkt.STATUS_APPROVED.

        This app has been approved by a reviewer but is currently private and
        only visitble to the app authors.

        """
        return not self.disabled_by_user and self.status == mkt.STATUS_APPROVED

    def is_published(self):
        """
        True if the app status is mkt.STATUS_PUBLIC.

        This means we can display the app in listing pages and index it in our
        search backend.

        """
        return not self.disabled_by_user and self.status == mkt.STATUS_PUBLIC

    def is_incomplete(self):
        return self.status == mkt.STATUS_NULL

    def is_pending(self):
        return self.status == mkt.STATUS_PENDING

    def is_rejected(self):
        return self.status == mkt.STATUS_REJECTED

    def is_homescreen(self):
        return self.tags.filter(tag_text='homescreen').exists()

    @property
    def is_deleted(self):
        return self.status == mkt.STATUS_DELETED

    @property
    def is_disabled(self):
        """True if this Addon is disabled.

        It could be disabled by an admin or disabled by the developer
        """
        return self.status == mkt.STATUS_DISABLED or self.disabled_by_user

    def can_become_premium(self):
        if self.upsell or self.is_premium():
            return False
        return True

    def is_premium(self):
        """
        If the addon is premium. Will include addons that are premium
        and have a price of zero. Primarily of use in the devhub to determine
        if an app is intending to be premium.
        """
        return self.premium_type in mkt.ADDON_PREMIUMS

    def is_free(self):
        """
        This is the opposite of is_premium. Will not include apps that have a
        price of zero. Primarily of use in the devhub to determine if an app is
        intending to be free.
        """
        return not (self.is_premium() and self.premium and
                    self.premium.price)

    def is_free_inapp(self):
        return self.premium_type == mkt.ADDON_FREE_INAPP

    def needs_payment(self):
        return (self.premium_type not in
                (mkt.ADDON_FREE, mkt.ADDON_OTHER_INAPP))

    def can_be_deleted(self):
        return not self.is_deleted

    @classmethod
    def _last_updated_queries(cls):
        """
        Get the queries used to calculate addon.last_updated.
        """
        return (Webapp.objects
                .filter(status=mkt.STATUS_PUBLIC,
                        versions__files__status=mkt.STATUS_PUBLIC)
                .values('id')
                .annotate(last_updated=Max('versions__created')))

    @cached_property(writable=True)
    def all_previews(self):
        return list(self.get_previews())

    def get_previews(self):
        """Exclude promo graphics."""
        return self.previews.exclude(position=-1)

    def remove_locale(self, locale):
        """NULLify strings in this locale for the add-on and versions."""
        for o in itertools.chain([self], self.versions.all()):
            Translation.objects.remove_for(o, locale)

    def get_mozilla_contacts(self):
        return filter(None,
                      [x.strip() for x in self.mozilla_contact.split(',')])

    @cached_property
    def upsell(self):
        """Return the upsell or add-on, or None if there isn't one."""
        try:
            # We set unique_together on the model, so there will only be one.
            return self._upsell_from.all()[0]
        except IndexError:
            pass

    def has_author(self, user, roles=None):
        """True if ``user`` is an author with any of the specified ``roles``.

        ``roles`` should be a list of valid roles (see mkt.AUTHOR_ROLE_*). If
        not specified, has_author will return true if the user has any role.
        """
        if user is None or user.is_anonymous():
            return False
        if roles is None:
            roles = dict(mkt.AUTHOR_CHOICES).keys()
        return AddonUser.objects.filter(addon=self, user=user,
                                        role__in=roles).exists()

    def get_purchase_type(self, user):
        if user and isinstance(user, UserProfile):
            try:
                return self.addonpurchase_set.get(user=user).type
            except models.ObjectDoesNotExist:
                pass

    def has_purchased(self, user):
        return self.get_purchase_type(user) == mkt.CONTRIB_PURCHASE

    def is_refunded(self, user):
        return self.get_purchase_type(user) == mkt.CONTRIB_REFUND

    def is_chargeback(self, user):
        return self.get_purchase_type(user) == mkt.CONTRIB_CHARGEBACK

    def can_review(self, user):
        if user and self.has_author(user):
            return False
        else:
            return (not self.is_premium() or self.has_purchased(user) or
                    self.is_refunded(user))

    def get_latest_file(self):
        """Get the latest file from the current version."""
        cur = self.current_version
        if cur:
            res = cur.files.order_by('-created')
            if res:
                return res[0]

    @property
    def uses_flash(self):
        """
        Convenience property until more sophisticated per-version
        checking is done for packaged apps.
        """
        f = self.get_latest_file()
        if not f:
            return False
        return f.uses_flash

    def in_escalation_queue(self):
        return self.escalationqueue_set.exists()

    def update_names(self, new_names):
        """
        Adds, edits, or removes names to match the passed in new_names dict.
        Will not remove the translation of the default_locale.

        `new_names` is a dictionary mapping of locales to names.

        Returns a message that can be used in logs showing what names were
        added or updated.

        Note: This method doesn't save the changes made to the addon object.
        Don't forget to call save() in your calling method.
        """
        updated_locales = {}
        locales = dict(Translation.objects.filter(id=self.name_id)
                                          .values_list('locale',
                                                       'localized_string'))
        msg_c = []  # For names that were created.
        msg_d = []  # For deletes.
        msg_u = []  # For updates.

        # Normalize locales.
        names = {}
        for locale, name in new_names.iteritems():
            loc = find_language(locale)
            if loc and loc not in names:
                names[loc] = name

        # Null out names no longer in `names` but exist in the database.
        for locale in set(locales) - set(names):
            names[locale] = None

        for locale, name in names.iteritems():

            if locale in locales:
                if not name and locale.lower() == self.default_locale.lower():
                    pass  # We never want to delete the default locale.
                elif not name:  # A deletion.
                    updated_locales[locale] = None
                    msg_d.append(u'"%s" (%s).' % (locales.get(locale), locale))
                elif name != locales[locale]:
                    updated_locales[locale] = name
                    msg_u.append(u'"%s" -> "%s" (%s).' % (
                        locales[locale], name, locale))
            else:
                updated_locales[locale] = names.get(locale)
                msg_c.append(u'"%s" (%s).' % (name, locale))

        if locales != updated_locales:
            self.name = updated_locales

        return {
            'added': ' '.join(msg_c),
            'deleted': ' '.join(msg_d),
            'updated': ' '.join(msg_u),
        }

    def update_default_locale(self, locale):
        """
        Updates default_locale if it's different and matches one of our
        supported locales.

        Returns tuple of (old_locale, new_locale) if updated. Otherwise None.
        """
        old_locale = self.default_locale
        locale = find_language(locale)
        if locale and locale != old_locale:
            self.update(default_locale=locale)
            return old_locale, locale
        return None

    @property
    def premium(self):
        """
        Returns the premium object which will be gotten by the transformer,
        if its not there, try and get it. Will return None if there's nothing
        there.
        """
        if not hasattr(self, '_premium'):
            try:
                self._premium = self.addonpremium
            except AddonPremium.DoesNotExist:
                self._premium = None
        return self._premium

    def has_installed(self, user):
        if not user or not isinstance(user, UserProfile):
            return False
        return self.installed.filter(user=user).exists()

    @cached_property
    def upsold(self):
        """
        Return what this is going to upsold from,
        or None if there isn't one.
        """
        try:
            return self._upsell_to.all()[0]
        except IndexError:
            pass

    @classmethod
    def get_fallback(cls):
        return cls._meta.get_field('default_locale')

    @cached_property(writable=True)
    def listed_authors(self):
        return UserProfile.objects.filter(
            addons=self,
            addonuser__listed=True).order_by('addonuser__position')

    @property
    def reviews(self):
        return Review.objects.filter(addon=self, reply_to=None)

    def get_icon_dir(self):
        return os.path.join(settings.ADDON_ICONS_PATH, str(self.id / 1000))

    def get_icon_url(self, size):
        return get_icon_url(static_url('ADDON_ICON_URL'), self, size)

    def get_promo_img_dir(self):
        return os.path.join(settings.WEBAPP_PROMO_IMG_PATH,
                            str(self.id / 1000))

    def get_promo_img_url(self, size):
        if not self.promo_img_hash:
            return ''
        return get_promo_img_url(static_url('WEBAPP_PROMO_IMG_URL'), self,
                                 size,
                                 default_format='webapp-promo-img-{size}.png')

    @staticmethod
    def transformer(apps):
        if not apps:
            return
        apps_dict = dict((a.id, a) for a in apps)

        # Set _latest_version, _current_version
        Webapp.attach_related_versions(apps, apps_dict)

        # Attach previews. Don't use transforms, the only one present is for
        # translations and Previews don't have captions in the Marketplace, and
        # therefore don't have translations.
        Webapp.attach_previews(apps, apps_dict, no_transforms=True)

        # Attach AddonPremium instances.
        Webapp.attach_premiums(apps, apps_dict)

        # FIXME: re-use attach_devices instead ?
        for adt in AddonDeviceType.objects.filter(addon__in=apps_dict):
            if not getattr(apps_dict[adt.addon_id], '_device_types', None):
                apps_dict[adt.addon_id]._device_types = []
            apps_dict[adt.addon_id]._device_types.append(
                DEVICE_TYPES[adt.device_type])

        # FIXME: attach geodata and content ratings. Maybe in a different
        # transformer that would then be called automatically for the API ?

    @staticmethod
    def version_and_file_transformer(apps):
        """Attach all the versions and files to the apps."""
        # Don't just return an empty list, it will break code that expects
        # a query object
        if not len(apps):
            return apps

        ids = set(app.id for app in apps)
        versions = (Version.objects.filter(addon__in=ids)
                    .select_related('addon'))
        vids = [v.id for v in versions]
        files = (File.objects.filter(version__in=vids)
                             .select_related('version'))

        # Attach the files to the versions.
        f_dict = dict((k, list(vs)) for k, vs in
                      sorted_groupby(files, 'version_id'))
        for version in versions:
            version.all_files = f_dict.get(version.id, [])
        # Attach the versions to the apps.
        v_dict = dict((k, list(vs)) for k, vs in
                      sorted_groupby(versions, 'addon_id'))
        for app in apps:
            app.all_versions = v_dict.get(app.id, [])

        return apps

    def get_public_version(self):
        """Retrieves the latest PUBLIC version of an addon."""
        if self.status not in mkt.WEBAPPS_APPROVED_STATUSES:
            # Apps that aren't in an approved status have no current version.
            return None

        try:
            return (self.versions
                    .filter(files__status=mkt.STATUS_PUBLIC)
                    .extra(where=[
                        """
                        NOT EXISTS (
                            SELECT 1 FROM versions as v2
                            INNER JOIN files AS f2 ON (f2.version_id = v2.id)
                            WHERE v2.id = versions.id
                            AND f2.status != %s)""" % mkt.STATUS_PUBLIC])[0])

        except (IndexError, Version.DoesNotExist):
            return None

    @use_master
    def update_version(self, ignore=None, _signal=True):
        """
        Returns true if we updated the field.

        The optional ``ignore`` parameter, if present, is a version to not
        consider as part of the update, since it may be in the process of being
        deleted.

        Pass ``_signal=False`` if you want to no signals fired at all.

        """
        current = self.get_public_version()

        try:
            latest_qs = self.versions.all()
            if ignore is not None:
                latest_qs = latest_qs.exclude(pk=ignore.pk)
            latest = latest_qs.latest()
        except Version.DoesNotExist:
            latest = None
        latest_id = latest and latest.id

        diff = [self._current_version, current]

        # Sometimes the DB is in an inconsistent state when this
        # signal is dispatched.
        try:
            if self._latest_version:
                # Make sure stringifying this does not trigger
                # Version.DoesNotExist before trying to use it for
                # logging.
                unicode(self._latest_version)
            diff += [self._latest_version, latest]
        except Version.DoesNotExist:
            diff += [self._latest_version_id, latest_id]

        updated = {}
        send_signal = False
        if self._current_version != current:
            updated.update({'_current_version': current})
            send_signal = True
        # Don't use self.latest_version here. It may throw Version.DoesNotExist
        # if we're called from a post_delete signal. We also don't set
        # send_signal since we only want this fired if the public version
        # changes.
        if self._latest_version_id != latest_id:
            updated.update({'_latest_version': latest})

        # update_version can be called by a post_delete signal (such
        # as File's) when deleting a version. If so, we should avoid putting
        # that version-being-deleted in any fields.
        if ignore is not None:
            updated = dict([(k, v)
                            for (k, v) in updated.iteritems() if v != ignore])

        if updated:
            # Pass along _signal to the .update() to prevent it from firing
            # signals if we don't want them.
            updated['_signal'] = _signal
            try:
                self.update(**updated)
                if send_signal and _signal:
                    signals.version_changed.send(sender=self)
                log.info(u'Version changed from current: %s to %s, '
                         u'latest: %s to %s for addon %s'
                         % tuple(diff + [self]))
            except Exception, e:
                log.error(u'Could not save version changes '
                          u'current: %s to %s, latest: %s to %s '
                          u'for addon %s (%s)'
                          % tuple(diff + [self, e]))

        return bool(updated)

    @property
    def current_version(self):
        """Returns the current_version or None if the app is deleted or not
        created yet"""
        if not self.id or self.status == mkt.STATUS_DELETED:
            return None
        try:
            return self._current_version
        except ObjectDoesNotExist:
            pass
        return None

    @property
    def latest_version(self):
        """Returns the latest_version or None if the app is deleted or not
        created yet"""
        if not self.id or self.status == mkt.STATUS_DELETED:
            return None
        try:
            return self._latest_version
        except ObjectDoesNotExist:
            pass
        return None

    @property
    def geodata(self):
        if hasattr(self, '_geodata'):
            return self._geodata
        return Geodata.objects.get_or_create(addon=self)[0]

    def get_api_url(self, action=None, api=None, resource=None, pk=False):
        """Reverse a URL for the API."""
        if pk:
            key = self.pk
        else:
            key = self.app_slug
        return reverse('app-detail', kwargs={'pk': key})

    def get_url_path(self, src=None):
        url_ = reverse('detail', args=[self.app_slug])
        if src is not None:
            return urlparams(url_, src=src)
        return url_

    def get_detail_url(self, action=None):
        """Reverse URLs for 'detail', 'details.record', etc."""
        return reverse(('detail.%s' % action) if action else 'detail',
                       args=[self.app_slug])

    def get_purchase_url(self, action=None, args=None):
        """Reverse URLs for 'purchase', 'purchase.done', etc."""
        return reverse(('purchase.%s' % action) if action else 'purchase',
                       args=[self.app_slug] + (args or []))

    def get_dev_url(self, action='edit', args=None, prefix_only=False):
        # Either link to the "new" Marketplace Developer Hub or the old one.
        args = args or []
        prefix = 'mkt.developers'
        view_name = ('%s.%s' if prefix_only else '%s.apps.%s')
        return reverse(view_name % (prefix, action),
                       args=[self.app_slug] + args)

    def get_ratings_url(self, action='list', args=None):
        """Reverse URLs for 'ratings.list', 'ratings.add', etc."""
        return reverse(('ratings.%s' % action),
                       args=[self.app_slug] + (args or []))

    def get_stats_url(self):
        return reverse('commonplace.stats.app_dashboard', args=[self.app_slug])

    def get_comm_thread_url(self):
        return reverse('commonplace.commbadge.app_dashboard',
                       args=[self.app_slug])

    @staticmethod
    def domain_from_url(url, allow_none=False):
        if not url:
            if allow_none:
                return
            raise ValueError('URL was empty')
        pieces = urlparse.urlparse(url)
        return '%s://%s' % (pieces.scheme, pieces.netloc.lower())

    @property
    def punycode_app_domain(self):
        if self.app_domain:
            return self.app_domain.encode('idna')

    @property
    def parsed_app_domain(self):
        if self.is_packaged:
            raise ValueError('Packaged apps do not have a domain')
        return urlparse.urlparse(self.app_domain)

    @property
    def device_types(self):
        # If the transformer attached something, use it.
        if hasattr(self, '_device_types'):
            return self._device_types
        return [DEVICE_TYPES[d.device_type] for d in
                self.addondevicetype_set.order_by('device_type')]

    @property
    def origin(self):
        if self.is_packaged:
            return self.app_domain

        parsed = urlparse.urlparse(self.get_manifest_url())
        return '%s://%s' % (parsed.scheme, parsed.netloc)

    def language_ascii(self):
        lang = translation.to_language(self.default_locale)
        return settings.LANGUAGES.get(lang)

    def get_manifest_url(self, reviewer=False):
        """
        Hosted apps: a URI to an external manifest.
        Packaged apps: a URI to a mini manifest on m.m.o. If reviewer, the
        mini-manifest behind reviewer auth pointing to the reviewer-signed
        package.
        """
        if self.is_packaged:
            if reviewer and self.latest_version:
                # Get latest version and return reviewer manifest URL.
                version = self.latest_version
                return absolutify(reverse('reviewers.mini_manifest',
                                          args=[self.app_slug, version.id]))
            elif self.current_version:
                return absolutify(reverse('detail.manifest', args=[self.guid]))
            else:
                return ''  # No valid version.
        else:
            return self.manifest_url

    def has_icon_in_manifest(self, file_obj=None):
        data = self.get_manifest_json(file_obj)
        return 'icons' in data

    def get_manifest_json(self, file_obj=None):
        file_ = file_obj or self.get_latest_file()
        if not file_:
            return {}

        try:
            return file_.version.manifest
        except AppManifest.DoesNotExist:
            # TODO: Remove this when we're satisified the above is working.
            log.info('Falling back to loading manifest from file system. '
                     'Webapp:%s File:%s' % (self.id, file_.id))
            if file_.status == mkt.STATUS_DISABLED:
                file_path = file_.guarded_file_path
            else:
                file_path = file_.file_path

            return WebAppParser().get_json_data(file_path)

    def manifest_updated(self, manifest, upload):
        """The manifest has updated, update the version and file.

        This is intended to be used for hosted apps only, which have only a
        single version and a single file.
        """
        data = parse_addon(upload, self)
        manifest = WebAppParser().get_json_data(upload)
        version = self.versions.latest()
        max_ = Version._meta.get_field_by_name('_developer_name')[0].max_length
        version.update(version=data['version'],
                       _developer_name=data['developer_name'][:max_])
        try:
            version.manifest_json.update(manifest=json.dumps(manifest))
        except AppManifest.DoesNotExist:
            AppManifest.objects.create(version=version,
                                       manifest=json.dumps(manifest))
        path = smart_path(nfd_str(upload.path))
        file = version.files.latest()
        file.filename = file.generate_filename(extension='.webapp')
        file.size = private_storage.size(path)
        file.hash = file.generate_hash(path)
        log.info('Updated file hash to %s' % file.hash)
        file.save()

        # Move the uploaded file from the temp location.
        copy_stored_file(
            path, os.path.join(version.path_prefix, nfd_str(file.filename)),
            src_storage=private_storage, dst_storage=private_storage)
        log.info('[Webapp:%s] Copied updated manifest to %s' % (
            self, version.path_prefix))

        mkt.log(mkt.LOG.MANIFEST_UPDATED, self)

    def has_incomplete_status(self):
        return self.is_incomplete()

    def details_errors(self):
        """
        See if initial app submission is complete (details).
        Returns list of reasons app may not be complete.
        """
        reasons = []

        if not self.support_email and not self.support_url:
            reasons.append(_('You must provide a support email or URL.'))
        if not self.name:
            reasons.append(_('You must provide an app name.'))
        if not self.device_types:
            reasons.append(_('You must provide at least one device type.'))

        if not self.categories:
            reasons.append(_('You must provide at least one category.'))
        if not self.previews.count():
            reasons.append(_('You must upload at least one screenshot or '
                             'video.'))
        return reasons

    def details_complete(self):
        """
        Checks if app detail submission is complete (first step of submit).
        """
        return not self.details_errors()

    def is_rated(self):
        return self.content_ratings.exists()

    def all_payment_accounts(self):
        # TODO: cache this somehow. Using @cached_property was hard because
        # there's no easy way to invalidate something that should be
        # recalculated.
        return (self.app_payment_accounts.select_related('payment_account')
                .all())

    def payment_account(self, provider_id):
        from mkt.developers.models import AddonPaymentAccount

        qs = (self.app_payment_accounts.select_related('payment_account')
              .filter(payment_account__provider=provider_id))

        try:
            return qs.get()
        except AddonPaymentAccount.DoesNotExist, exc:
            log.info('non-existant payment account for app {app}: '
                     '{exc.__class__.__name__}: {exc}'
                     .format(app=self, exc=exc))

            raise self.PayAccountDoesNotExist(
                'No payment account for {app} named {pr}. '
                'Choices: {all}'
                .format(app=self,
                        pr=PROVIDER_CHOICES[provider_id],
                        all=[PROVIDER_CHOICES[a.payment_account.provider]
                             for a in self.all_payment_accounts()]))

    def has_payment_account(self):
        """True if app has at least one payment account."""
        return bool(self.all_payment_accounts().count())

    def has_multiple_payment_accounts(self):
        """True if the app has more than one payment account."""
        return self.all_payment_accounts().count() > 1

    def payments_complete(self):
        """Also returns True if the app doesn't needs payments."""
        return not self.needs_payment() or self.has_payment_account()

    def completion_errors(self, ignore_ratings=False):
        """
        Compiles all submission steps into a single error report.

        ignore_ratings -- doesn't check for content_ratings for cases in which
                          content ratings were just created.
        """
        errors = {}

        if not self.details_complete():
            errors['details'] = self.details_errors()
        if not ignore_ratings and not self.is_rated():
            errors['content_ratings'] = _('You must set up content ratings.')
        if not self.payments_complete():
            errors['payments'] = _('You must set up a payment account.')

        return errors

    def completion_error_msgs(self):
        """Returns submission error messages as a flat list."""
        errors = self.completion_errors()
        # details is a list of msgs instead of a string like others.
        detail_errors = errors.pop('details', []) or []
        return detail_errors + errors.values()

    def is_fully_complete(self, ignore_ratings=False):
        """
        Wrapper to submission errors for readability and testability (mocking).
        """
        return not self.completion_errors(ignore_ratings)

    def next_step(self):
        """
        Gets the next step to fully complete app submission.
        """
        if self.has_incomplete_status() and not self.details_complete():
            # Some old public apps may have some missing detail fields.
            return {
                'name': _('Details'),
                'description': _('This app\'s submission process has not been '
                                 'fully completed.'),
                'url': self.get_dev_url(),
            }
        elif not self.is_rated():
            return {
                'name': _('Content Ratings'),
                'description': _('This app needs to get a content rating.'),
                'url': self.get_dev_url('ratings'),
            }
        elif not self.payments_complete():
            return {
                'name': _('Payments'),
                'description': _('This app needs a payment account set up.'),
                'url': self.get_dev_url('payments'),
            }

    def guess_is_offline(self):
        """
        Returns a boolean of whether this is an app that degrades
        gracefully offline (i.e., is a packaged app or has an
        `appcache_path` defined in its manifest).

        """
        if self.is_packaged:
            return True
        elif self.latest_version and self.latest_version.all_files:
            # Manually find the latest file since `self.get_latest_file()`
            # won't be set correctly near the start of the app submission
            # process.
            manifest = self.get_manifest_json(
                file_obj=self.latest_version.all_files[0])
            return bool(manifest and 'appcache_path' in manifest)
        else:
            return False

    def mark_done(self):
        """When the submission process is done, update status accordingly."""
        self.update(status=mkt.WEBAPPS_UNREVIEWED_STATUS)

    def update_status(self, **kwargs):
        if self.is_deleted or self.status == mkt.STATUS_BLOCKED:
            return

        def _log(reason, old=self.status):
            log.info(u'Update app status [%s]: %s => %s (%s).' % (
                self.id, old, self.status, reason))
            mkt.log(mkt.LOG.CHANGE_STATUS, self.get_status_display(), self)

        # Handle the case of no versions.
        if not self.versions.exists():
            self.update(status=mkt.STATUS_NULL)
            _log('no versions')
            return

        # Handle the case of versions with no files.
        if not self.versions.filter(files__isnull=False).exists():
            self.update(status=mkt.STATUS_NULL)
            _log('no versions with files')
            return

        # If the app is incomplete, don't update status.
        if not self.is_fully_complete():
            return

        # If there are no public versions and at least one pending, set status
        # to pending.
        has_public = self.versions.filter(
            files__status=mkt.STATUS_PUBLIC).exists()
        has_approved = self.versions.filter(
            files__status=mkt.STATUS_APPROVED).exists()
        has_pending = self.versions.filter(
            files__status=mkt.STATUS_PENDING).exists()

        # If no public versions but there are approved versions, set app to
        # approved.
        if not has_public and has_approved:
            _log('has approved but no public files')
            self.update(status=mkt.STATUS_APPROVED)
            return

        # If no public versions but there are pending versions, set app to
        # pending.
        if not has_public and has_pending and not self.is_pending():
            self.update(status=mkt.STATUS_PENDING)
            _log('has pending but no public files')
            return

    def authors_other_addons(self, app=None):
        """Return other apps by the same author."""
        return (self.__class__.objects.visible()
                              .exclude(id=self.id).distinct()
                              .filter(addonuser__listed=True,
                                      authors__in=self.listed_authors))

    def can_be_purchased(self):
        return self.is_premium() and self.status in mkt.REVIEWED_STATUSES

    def can_purchase(self):
        return self.is_premium() and self.premium and self.is_public()

    def is_purchased(self, user):
        return user and self.id in user.purchase_ids()

    def has_premium(self):
        """If the app is premium status and has a premium object."""
        return bool(self.is_premium() and self.premium)

    def _setup_price_lookups(self, region, provider):
        """
        Alter the lookups for regions and provider.

        If RESTOFWORLD is not excluded, add it in.
        If the payment provider is not specified, set it to the default.
        """
        from mkt.developers.providers import ALL_PROVIDERS
        regions = []
        excluded = self.get_excluded_region_ids()

        # Don't allow the region if its excluded.
        if region not in excluded:
            regions.append(region)

        # Don't add in rest of the world if its excluded either.
        if (RESTOFWORLD != region and RESTOFWORLD.id not in excluded):
            regions.append(RESTOFWORLD.id)

        if not provider:
            provider = (
                ALL_PROVIDERS[settings.DEFAULT_PAYMENT_PROVIDER].provider)

        return regions, provider

    def get_price(self, carrier=None, region=None, provider=None):
        """
        A shortcut to get the price as decimal. Returns None if their is no
        price for the app.

        :param optional carrier: an int for the carrier.
        :param optional region: an int for the region. If RESTOFWORLD
            is not excluded, it will be added as a region fallback.
        :param optional provider: an int for the provider. Defaults to
            settings.DEFAULT_PAYMENT_PROVIDER.
        """
        regions, provider = self._setup_price_lookups(region, provider)
        if self.has_premium() and self.premium.price:
            return self.premium.price.get_price(carrier=carrier,
                                                regions=regions,
                                                provider=provider)

    def get_price_locale(self, carrier=None, region=None, provider=None):
        """
        A shortcut to get the localised price with currency. Returns None if
        their is no price for the app.

        :param optional carrier: an int for the carrier.
        :param optional region: an int for the region. If RESTOFWORLD
            is not excluded, it will be added as a region fallback.
        :param optional provider: an int for the provider. Defaults to
            settings.DEFAULT_PAYMENT_PROVIDER.
        """
        regions, provider = self._setup_price_lookups(region, provider)
        if self.has_premium() and self.premium.price:
            return self.premium.price.get_price_locale(
                carrier=carrier, regions=regions, provider=provider)

    def get_tier(self):
        """
        Returns the price tier object.
        """
        if self.has_premium():
            return self.premium.price

    def get_tier_name(self):
        """
        Returns the price tier for showing prices in the reviewer
        tools and developer hub.
        """
        tier = self.get_tier()
        if tier:
            return tier.tier_locale()

    @cached_property
    def promo(self):
        return self.get_promo()

    def get_promo(self):
        try:
            return self.previews.filter(position=-1)[0]
        except IndexError:
            pass

    def get_region_ids(self, restofworld=False, excluded=None):
        """
        Return IDs of regions in which this app is listed.

        If `excluded` is provided we'll use that instead of doing our own
        excluded lookup.
        """
        if restofworld:
            all_ids = mkt.regions.ALL_REGION_IDS
        else:
            all_ids = mkt.regions.REGION_IDS
        if excluded is None:
            excluded = self.get_excluded_region_ids()

        return sorted(set(all_ids) - set(excluded or []))

    def get_excluded_region_ids(self):
        """
        Return IDs of regions for which this app is excluded.

        This will be all the addon excluded regions. If the app is premium,
        this will also exclude any region that does not have the price tier
        set.

        Note: free and in-app are not included in this.
        """
        excluded = set(self.addonexcludedregion
                           .values_list('region', flat=True))

        if self.is_premium():
            all_regions = set(mkt.regions.ALL_REGION_IDS)
            # Find every region that does not have payments supported
            # and add that into the exclusions.
            #
            # All the regions that are currently paid for an app.
            price_ids = self.get_price_region_ids()
            if RESTOFWORLD.id in excluded or RESTOFWORLD.id not in price_ids:
                # If the "rest of the world" is excluded or its not in the
                # list of valid price ids then we need to exclude all
                # countries that don't have payments.
                excluded = excluded.union(all_regions.difference(price_ids))

        geo = self.geodata
        if geo.region_de_iarc_exclude or geo.region_de_usk_exclude:
            excluded.add(mkt.regions.DEU.id)
        if geo.region_br_iarc_exclude:
            excluded.add(mkt.regions.BRA.id)

        return sorted(list(excluded))

    def get_price_region_ids(self):
        tier = self.get_tier()
        if tier:
            return sorted(p['region'] for p in tier.prices() if p['paid'])
        return []

    def get_regions(self, regions=None, sort_by='slug'):
        """
        Return a list of regions objects the app is available in, e.g.:
             [<class 'mkt.constants.regions.GBR'>,...]

        if `regions` is provided we'll use that instead of calling
        self.get_region_ids()
        """
        regions_ids = regions or self.get_region_ids(restofworld=True)
        _regions = map(mkt.regions.REGIONS_CHOICES_ID_DICT.get, regions_ids)
        return sorted(_regions, key=operator.attrgetter(sort_by))

    def listed_in(self, region=None, category=None):
        listed = []
        if region:
            listed.append(region.id in self.get_region_ids(restofworld=True))
        if category:
            listed.append(category in (self.categories or []))
        return all(listed or [False])

    def content_ratings_in(self, region, category=None):
        """
        Get all content ratings for this app in REGION for CATEGORY.
        (e.g. give me the content ratings for a game listed in a Brazil.)
        """

        # If we want to find games in Brazil with content ratings, then
        # make sure it's actually listed in Brazil and it's a game.
        if category and not self.listed_in(region, category):
            return []

        rb = []
        if not region.ratingsbody:
            # If a region doesn't specify a ratings body, default to GENERIC.
            rb = mkt.ratingsbodies.GENERIC.id
        else:
            rb = region.ratingsbody.id

        return list(self.content_ratings.filter(ratings_body=rb)
                        .order_by('rating'))

    @classmethod
    def now(cls):
        return datetime.date.today()

    def in_rereview_queue(self):
        return self.rereviewqueue_set.exists()

    def in_tarako_queue(self):
        from mkt.reviewers.models import QUEUE_TARAKO
        return self.additionalreview_set.unreviewed(queue=QUEUE_TARAKO)

    def in_china_queue(self):
        china_queue = self.__class__.objects.pending_in_region(mkt.regions.CHN)
        return china_queue.filter(pk=self.pk).exists()

    def get_package_path(self):
        """Returns the `package_path` if the app is packaged."""
        if not self.is_packaged:
            return

        version = self.current_version
        if not version:
            return

        try:
            file_obj = version.all_files[0]
        except IndexError:
            return
        else:
            return absolutify(
                os.path.join(reverse('downloads.file', args=[file_obj.id]),
                             file_obj.filename))

    def get_cached_manifest(self, force=False):
        """
        Build, cache and return the "mini" manifest + corresponding etag
        for this app.

        Call this with `force=True` whenever we need to update the cached
        version of this manifest, e.g., when a new version of the packaged app
        is approved.

        If the addon is not a packaged app, this will not cache anything.

        Ensure that the calling method checks various permissions if needed.
        E.g. see mkt/detail/views.py. This is also called as a task after
        reviewer approval so we can't perform some checks here.
        """
        if not self.is_packaged:
            return

        return get_cached_minifest(self, force=force)

    def sign_if_packaged(self, version_pk=None, reviewer=False):
        if not self.is_packaged:
            return
        if version_pk is None:
            version_pk = self.current_version.pk
        return packaged.sign(version_pk, reviewer=reviewer)

    def is_premium_type_upgrade(self, premium_type):
        """
        Returns True if changing self.premium_type from current value to passed
        in value is considered an upgrade that should trigger a re-review.
        """
        ALL = set(mkt.ADDON_FREES + mkt.ADDON_PREMIUMS)
        free_upgrade = ALL - set([mkt.ADDON_FREE])
        free_inapp_upgrade = ALL - set([mkt.ADDON_FREE, mkt.ADDON_FREE_INAPP])

        if (self.premium_type == mkt.ADDON_FREE and
                premium_type in free_upgrade):
            return True
        if (self.premium_type == mkt.ADDON_FREE_INAPP and
                premium_type in free_inapp_upgrade):
            return True
        return False

    def create_blocklisted_version(self):
        """
        Creates a new version who's file is the blocklisted app found in /media
        and sets status to STATUS_BLOCKLISTED.

        """
        blocklisted_path = os.path.join(settings.MEDIA_ROOT, 'packaged-apps',
                                        'blocklisted.zip')
        v = Version.objects.create(addon=self, version='blocklisted')
        f = File(version=v, status=mkt.STATUS_BLOCKED)
        f.filename = f.generate_filename()
        copy_stored_file(
            blocklisted_path, f.file_path,
            src_storage=local_storage, dst_storage=private_storage)
        log.info(u'[Webapp:%s] Copied blocklisted app from %s to %s' % (
            self.id, blocklisted_path, f.file_path))
        f.size = private_storage.size(f.file_path)
        f.hash = f.generate_hash(f.file_path)
        f.save()
        mf = WebAppParser().get_json_data(private_storage.open(f.file_path))
        AppManifest.objects.create(version=v, manifest=json.dumps(mf))
        self.sign_if_packaged(v.pk)
        self.status = mkt.STATUS_BLOCKED
        self._current_version = v
        self.save()

    def update_name_from_package_manifest(self):
        """
        Looks at the manifest.webapp inside the current version's file and
        updates the app's name and translated names.

        Note: Make sure the correct version is in place before calling this.
        """
        if not self.is_packaged:
            return None

        file_ = self.current_version.all_files[0]
        mf = self.get_manifest_json(file_)

        # Get names in "locales" as {locale: name}.
        locale_names = get_locale_properties(mf, 'name', self.default_locale)

        # Check changes to default_locale.
        locale_changed = self.update_default_locale(mf.get('default_locale'))
        if locale_changed:
            log.info(u'[Webapp:%s] Default locale changed from "%s" to "%s".'
                     % (self.pk, locale_changed[0], locale_changed[1]))

        # Update names
        crud = self.update_names(locale_names)
        if any(crud.values()):
            self.save()

    def update_supported_locales(self, latest=False, manifest=None):
        """
        Loads the manifest (for either hosted or packaged) and updates
        Version.supported_locales for the current version or latest version if
        latest=True.
        """
        version = self.versions.latest() if latest else self.current_version

        if not manifest:
            file_ = version.all_files[0]
            manifest = self.get_manifest_json(file_)

        updated = False

        supported_locales = ','.join(get_supported_locales(manifest))
        if version.supported_locales != supported_locales:
            updated = True
            version.update(supported_locales=supported_locales, _signal=False)

        return updated

    @property
    def app_type_id(self):
        """
        Returns int of `1` (hosted), `2` (packaged), or `3` (privileged).
        Used by ES.
        """
        if self.latest_version and self.latest_version.is_privileged:
            return mkt.ADDON_WEBAPP_PRIVILEGED
        elif self.is_packaged:
            return mkt.ADDON_WEBAPP_PACKAGED
        return mkt.ADDON_WEBAPP_HOSTED

    @property
    def app_type(self):
        """
        Returns string of 'hosted', 'packaged', or 'privileged'.
        Used in the API.
        """
        return mkt.ADDON_WEBAPP_TYPES[self.app_type_id]

    def check_ownership(self, request, require_owner, require_author,
                        ignore_disabled, admin):
        """
        Used by acl.check_ownership to see if request.user has permissions for
        the addon.
        """
        if require_author:
            require_owner = False
            ignore_disabled = True
            admin = False
        return acl.check_addon_ownership(request, self, admin=admin,
                                         viewer=(not require_owner),
                                         ignore_disabled=ignore_disabled)

    @property
    def supported_locales(self):
        """
        Returns a tuple of the form:

            (localized default_locale, list of localized supported locales)

        for the current public version.

        """
        languages = []
        version = self.current_version or self.latest_version

        if version:
            for locale in version.supported_locales.split(','):
                if locale:
                    language = settings.LANGUAGES.get(locale.lower())
                    if language:
                        languages.append(language)

        return (
            settings.LANGUAGES.get(self.default_locale.lower()),
            sorted(languages)
        )

    @property
    def developer_name(self):
        """This is the developer name extracted from the manifest."""
        version = self.current_version or self.latest_version
        if version:
            return version.developer_name

    @property
    def file_size(self):
        """App size whether it be size of a package or size of a hosted app."""
        try:
            try:
                return self.current_version.all_files[0].size
            except AttributeError:
                if self.latest_version:
                    return self.latest_version.all_files[0].size
        except IndexError:
            return

    def is_dummy_content_for_qa(self):
        """
        Returns whether this app is a dummy app used for testing only or not.
        """
        return self.pk == settings.QA_APP_ID

    def iarc_token(self):
        """
        Simple hash to verify token in pingback API.
        """
        return hashlib.sha512(settings.SECRET_KEY + str(self.id)).hexdigest()

    def get_content_ratings_by_body(self, es=False):
        """
        Gets content ratings on this app keyed by bodies.

        es -- denotes whether to return ES-friendly results (just the IDs of
              rating classes) to fetch and translate later.
        """
        content_ratings = {}
        for cr in self.content_ratings.all():
            body = cr.get_body()
            rating_serialized = {
                'body': body.id,
                'rating': cr.get_rating().id
            }
            if not es:
                rating_serialized = dehydrate_content_rating(rating_serialized)
            content_ratings[body.label] = rating_serialized

        return content_ratings

    def set_iarc_info(self, submission_id, security_code):
        """
        Sets the iarc_info for this app.
        """
        data = {'submission_id': submission_id,
                'security_code': security_code}
        info, created = IARCInfo.objects.safer_get_or_create(
            addon=self, defaults=data)
        if not created:
            info.update(**data)

    @use_master
    def set_content_ratings(self, data):
        """
        Central method for setting content ratings.

        This overwrites or creates ratings, it doesn't delete and expects data
        of the form::

            {<ratingsbodies class>: <rating class>, ...}

        """
        from . import tasks

        if not data:
            return

        log.info('IARC setting content ratings for app:%s:%s' %
                 (self.id, self.app_slug))

        for ratings_body, rating in data.items():
            cr, created = self.content_ratings.safer_get_or_create(
                ratings_body=ratings_body.id, defaults={'rating': rating.id})
            if not created:
                cr.update(rating=rating.id, modified=datetime.datetime.now())

        log.info('IARC content ratings set for app:%s:%s' %
                 (self.id, self.app_slug))

        geodata, c = Geodata.objects.get_or_create(addon=self)
        save = False

        # If app gets USK Rating Refused, exclude it from Germany.
        has_usk_refused = self.content_ratings.filter(
            ratings_body=mkt.ratingsbodies.USK.id,
            rating=mkt.ratingsbodies.USK_REJECTED.id).exists()
        save = geodata.region_de_usk_exclude != has_usk_refused
        geodata.region_de_usk_exclude = has_usk_refused

        # Un-exclude games in Brazil/Germany once they get a content rating.
        save = (save or
                geodata.region_br_iarc_exclude or
                geodata.region_de_iarc_exclude)
        geodata.region_br_iarc_exclude = False
        geodata.region_de_iarc_exclude = False

        # Un-disable apps that were disabled by the great IARC purge.
        if (self.status == mkt.STATUS_DISABLED and self.iarc_purged):
            self.update(status=mkt.STATUS_PUBLIC, iarc_purged=False)

        if save:
            geodata.save()
            log.info('Un-excluding IARC-excluded app:%s from br/de')

        tasks.index_webapps.delay([self.id])

    @use_master
    def set_descriptors(self, data):
        """
        Sets IARC rating descriptors on this app.

        data -- list of database flags ('has_usk_lang')
        """
        create_kwargs = {}
        for body in mkt.iarc_mappings.DESCS:
            for desc, db_flag in mkt.iarc_mappings.DESCS[body].items():
                create_kwargs[db_flag] = db_flag in data

        rd, created = RatingDescriptors.objects.get_or_create(
            addon=self, defaults=create_kwargs)
        if not created:
            rd.update(modified=datetime.datetime.now(),
                      **create_kwargs)

    @use_master
    def set_interactives(self, data):
        """
        Sets IARC interactive elements on this app.

        data -- list of database flags ('has_users_interact')
        """
        create_kwargs = {}
        for interactive, db_flag in mkt.iarc_mappings.INTERACTIVES.items():
            create_kwargs[db_flag] = db_flag in data

        ri, created = RatingInteractives.objects.get_or_create(
            addon=self, defaults=create_kwargs)
        if not created:
            ri.update(**create_kwargs)

    def set_iarc_storefront_data(self, disable=False):
        """Send app data to IARC for them to verify."""
        try:
            iarc_info = self.iarc_info
        except IARCInfo.DoesNotExist:
            # App wasn't rated by IARC, return.
            return

        release_date = datetime.date.today()

        if self.status in mkt.WEBAPPS_APPROVED_STATUSES:
            version = self.current_version
            if version and version.reviewed:
                release_date = version.reviewed
        elif self.status in mkt.WEBAPPS_EXCLUDED_STATUSES:
            # Using `_latest_version` since the property returns None when
            # deleted.
            version = self._latest_version
            # Send an empty string to signify the app was removed.
            release_date = ''
        else:
            # If not approved or one of the disabled statuses, we shouldn't be
            # calling SET_STOREFRONT_DATA. Ignore this call.
            return

        log.debug('Calling SET_STOREFRONT_DATA for app:%s' % self.id)

        xmls = []
        for cr in self.content_ratings.all():
            xmls.append(render_xml('set_storefront_data.xml', {
                'app_url': self.get_url_path(),
                'submission_id': iarc_info.submission_id,
                'security_code': iarc_info.security_code,
                'rating_system': cr.get_body().iarc_name,
                'release_date': '' if disable else release_date,
                'title': get_iarc_app_title(self),
                'company': version.developer_name if version else '',
                'rating': cr.get_rating().iarc_name,
                'descriptors': self.rating_descriptors.iarc_deserialize(
                    body=cr.get_body()),
                'interactive_elements':
                    self.rating_interactives.iarc_deserialize(),
            }))

        for xml in xmls:
            r = get_iarc_client('services').Set_Storefront_Data(XMLString=xml)
            log.debug('IARC result app:%s, rating_body:%s: %s' % (
                self.id, cr.get_body().iarc_name, r))

    def last_rated_time(self):
        """Most recent content rating modified time or None if not rated."""
        if self.is_rated():
            return self.content_ratings.order_by('-modified')[0].modified


class AddonUpsell(ModelBase):
    free = models.ForeignKey(Webapp, related_name='_upsell_from')
    premium = models.ForeignKey(Webapp, related_name='_upsell_to')

    class Meta:
        db_table = 'addon_upsell'
        unique_together = ('free', 'premium')

    def __unicode__(self):
        return u'Free: %s to Premium: %s' % (self.free, self.premium)

    @cached_property
    def premium_addon(self):
        """
        Return the premium version, or None if there isn't one.
        """
        try:
            return self.premium
        except Webapp.DoesNotExist:
            pass

    def cleanup(self):
        try:
            # Just accessing these may raise an error.
            assert self.free and self.premium
        except ObjectDoesNotExist:
            log.info('Deleted upsell: from %s, to %s' %
                     (self.free_id, self.premium_id))
            self.delete()


def cleanup_upsell(sender, instance, **kw):
    if 'raw' in kw:
        return

    both = Q(free=instance) | Q(premium=instance)
    for upsell in list(AddonUpsell.objects.filter(both)):
        upsell.cleanup()

dbsignals.post_delete.connect(cleanup_upsell, sender=Webapp,
                              dispatch_uid='addon_upsell')


class Installs(ModelBase):
    addon = models.ForeignKey(Webapp, related_name='popularity')
    value = models.FloatField(default=0.0)
    # When region=0, we count across all regions.
    region = models.PositiveIntegerField(null=False, default=0, db_index=True)

    class Meta:
        db_table = 'addons_installs'
        unique_together = ('addon', 'region')


class Trending(ModelBase):
    addon = models.ForeignKey(Webapp, related_name='trending')
    value = models.FloatField(default=0.0)
    # When region=0, it's trending using install counts across all regions.
    region = models.PositiveIntegerField(null=False, default=0, db_index=True)

    class Meta:
        db_table = 'addons_trending'
        unique_together = ('addon', 'region')


# Set translated_fields manually to avoid querying translations for addon
# fields we don't use.
Webapp._meta.translated_fields = [
    Webapp._meta.get_field('homepage'),
    Webapp._meta.get_field('privacy_policy'),
    Webapp._meta.get_field('name'),
    Webapp._meta.get_field('description'),
    Webapp._meta.get_field('support_email'),
    Webapp._meta.get_field('support_url'),
]


@receiver(dbsignals.post_save, sender=Webapp,
          dispatch_uid='webapp.search.index')
def update_search_index(sender, instance, **kw):
    from . import tasks
    if not kw.get('raw'):
        if instance.upsold and instance.upsold.free_id:
            tasks.index_webapps.delay([instance.upsold.free_id])
        tasks.index_webapps.delay([instance.id])


@receiver(dbsignals.post_save, sender=AddonUpsell,
          dispatch_uid='addonupsell.search.index')
def update_search_index_upsell(sender, instance, **kw):
    # When saving an AddonUpsell instance, reindex both apps to update their
    # upsell/upsold properties in ES.
    from . import tasks
    if instance.free:
        tasks.index_webapps.delay([instance.free.id])
    if instance.premium:
        tasks.index_webapps.delay([instance.premium.id])


models.signals.pre_save.connect(save_signal, sender=Webapp,
                                dispatch_uid='webapp_translations')


@receiver(signals.version_changed, dispatch_uid='update_cached_manifests')
def update_cached_manifests(sender, **kw):
    if not kw.get('raw') and sender.is_packaged:
        from mkt.webapps.tasks import update_cached_manifests
        update_cached_manifests.delay(sender.id)


@Webapp.on_change
def watch_status(old_attr={}, new_attr={}, instance=None, sender=None, **kw):
    """Set nomination date when app is pending review."""
    new_status = new_attr.get('status')
    if not new_status:
        return
    addon = instance
    old_status = old_attr['status']

    # Log all status changes.
    if old_status != new_status:
        log.info(
            '[Webapp:{id}] Status changed from {old_status}:{old_status_name} '
            'to {new_status}:{new_status_name}'.format(
                id=addon.id, old_status=old_status,
                old_status_name=mkt.STATUS_CHOICES_API.get(old_status,
                                                           'unknown'),
                new_status=new_status,
                new_status_name=mkt.STATUS_CHOICES_API[new_status]))

    if new_status == mkt.STATUS_PENDING and old_status != new_status:
        # We always set nomination date when app switches to PENDING, even if
        # previously rejected.
        try:
            latest = addon.versions.latest()
            log.debug('[Webapp:%s] Setting nomination date to now.' % addon.id)
            latest.update(nomination=datetime.datetime.now())
        except Version.DoesNotExist:
            log.debug('[Webapp:%s] Missing version, no nomination set.'
                      % addon.id)


@Webapp.on_change
def watch_disabled(old_attr={}, new_attr={}, instance=None, sender=None, **kw):
    attrs = dict((k, v) for k, v in old_attr.items()
                 if k in ('disabled_by_user', 'status'))
    qs = (File.objects.filter(version__addon=instance.id)
                      .exclude(version__deleted=True))
    if Webapp(**attrs).is_disabled and not instance.is_disabled:
        for f in qs:
            f.unhide_disabled_file()
    if instance.is_disabled and not Webapp(**attrs).is_disabled:
        for f in qs:
            f.hide_disabled_file()


@receiver(dbsignals.post_save, sender=Webapp,
          dispatch_uid='webapp.pre_generate_apk')
def pre_generate_apk(sender=None, instance=None, **kw):
    """
    Pre-generate an Android APK for a public app.
    """
    if kw.get('raw'):
        return
    if not getattr(settings, 'PRE_GENERATE_APKS', False):
        log.info('[Webapp:{a}] APK pre-generation is disabled.'
                 .format(a=instance.id))
        return
    from . import tasks
    generated = False
    if instance.status in mkt.WEBAPPS_APPROVED_STATUSES:
        app_devs = set(d.id for d in instance.device_types)
        if (mkt.DEVICE_MOBILE.id in app_devs or
                mkt.DEVICE_TABLET.id in app_devs):
            tasks.pre_generate_apk.delay(instance.id)
            generated = True

    log.info('[Webapp:{a}] APK pre-generated? {result}'
             .format(a=instance.id, result='YES' if generated else 'NO'))


class Installed(ModelBase):
    """Track WebApp installations."""
    addon = models.ForeignKey(Webapp, related_name='installed')
    user = models.ForeignKey('users.UserProfile')
    uuid = models.CharField(max_length=255, db_index=True, unique=True)
    # Because the addon could change between free and premium,
    # we need to store the state at time of install here.
    premium_type = models.PositiveIntegerField(
        null=True, default=None, choices=mkt.ADDON_PREMIUM_TYPES.items())
    install_type = models.PositiveIntegerField(
        db_index=True, default=apps.INSTALL_TYPE_USER,
        choices=apps.INSTALL_TYPES.items())

    class Meta:
        db_table = 'users_install'
        unique_together = ('addon', 'user', 'install_type')


@receiver(models.signals.post_save, sender=Installed)
def add_uuid(sender, **kw):
    if not kw.get('raw'):
        install = kw['instance']
        if not install.uuid and install.premium_type is None:
            install.uuid = ('%s-%s' % (install.pk, str(uuid.uuid4())))
            install.premium_type = install.addon.premium_type
            install.save()


class AddonExcludedRegion(ModelBase):
    """
    Apps are listed in all regions by default.
    When regions are unchecked, we remember those excluded regions.
    """
    addon = models.ForeignKey(Webapp, related_name='addonexcludedregion')
    region = models.PositiveIntegerField(
        choices=mkt.regions.REGIONS_CHOICES_ID, db_index=True)

    class Meta:
        db_table = 'addons_excluded_regions'
        unique_together = ('addon', 'region')

    def __unicode__(self):
        region = self.get_region()
        return u'%s: %s' % (self.addon, region.slug if region else None)

    def get_region(self):
        return mkt.regions.REGIONS_CHOICES_ID_DICT.get(self.region)


@memoize(prefix='get_excluded_in')
def get_excluded_in(region_id):
    """
    Return IDs of Webapp objects excluded from a particular region or excluded
    due to Geodata flags.
    """
    aers = list(AddonExcludedRegion.objects.filter(region=region_id)
                .values_list('addon', flat=True))

    # For pre-IARC unrated games in Brazil/Germany.
    geodata_qs = Q()
    region = parse_region(region_id)
    if region in (mkt.regions.BRA, mkt.regions.DEU):
        geodata_qs |= Q(**{'region_%s_iarc_exclude' % region.slug: True})
    # For USK_RATING_REFUSED apps in Germany.
    if region == mkt.regions.DEU:
        geodata_qs |= Q(**{'region_de_usk_exclude': True})

    geodata_exclusions = []
    if geodata_qs:
        geodata_exclusions = list(Geodata.objects.filter(geodata_qs)
                                  .values_list('addon', flat=True))
    return set(aers + geodata_exclusions)


@receiver(models.signals.post_save, sender=AddonExcludedRegion,
          dispatch_uid='clean_memoized_exclusions')
def clean_memoized_exclusions(sender, **kw):
    if not kw.get('raw'):
        cache.delete_many([memoize_key('get_excluded_in', k)
                           for k in mkt.regions.ALL_REGION_IDS])


class IARCInfo(ModelBase):
    """
    Stored data for IARC.
    """
    addon = models.OneToOneField(Webapp, related_name='iarc_info')
    submission_id = models.PositiveIntegerField(null=False)
    security_code = models.CharField(max_length=10)

    class Meta:
        db_table = 'webapps_iarc_info'

    def __unicode__(self):
        return u'app:%s' % self.addon.app_slug


class ContentRating(ModelBase):
    """
    Ratings body information about an app.
    """
    addon = models.ForeignKey(Webapp, related_name='content_ratings')
    ratings_body = models.PositiveIntegerField(
        choices=[(k, rb.name) for k, rb in
                 mkt.ratingsbodies.RATINGS_BODIES.items()],
        null=False)
    rating = models.PositiveIntegerField(null=False)

    class Meta:
        db_table = 'webapps_contentrating'
        unique_together = ('addon', 'ratings_body')

    def __unicode__(self):
        return u'%s: %s' % (self.addon, self.get_label())

    def get_regions(self):
        """Gives us a list of Region classes that use this rating body."""
        # All regions w/o specified ratings bodies fallback to Generic.
        generic_regions = []
        if self.get_body_class() == mkt.ratingsbodies.GENERIC:
            generic_regions = mkt.regions.ALL_REGIONS_WITHOUT_CONTENT_RATINGS()

        return ([x for x in mkt.regions.ALL_REGIONS_WITH_CONTENT_RATINGS()
                 if self.get_body_class() == x.ratingsbody] +
                list(generic_regions))

    def get_region_slugs(self):
        """Gives us the region slugs that use this rating body."""
        if self.get_body_class() == mkt.ratingsbodies.GENERIC:
            # For the generic rating body, we just pigeonhole all of the misc.
            # regions into one region slug, GENERIC. Reduces redundancy in the
            # final data structure. Rather than
            # {'pe': {generic_rating}, 'ar': {generic_rating}, etc}, generic
            # regions will just use single {'generic': {generic rating}}
            return [mkt.regions.GENERIC_RATING_REGION_SLUG]
        return [x.slug for x in self.get_regions()]

    def get_body_class(self):
        return mkt.ratingsbodies.RATINGS_BODIES[self.ratings_body]

    def get_body(self):
        """Ratings body instance with translated strings attached."""
        return mkt.ratingsbodies.dehydrate_ratings_body(self.get_body_class())

    def get_rating_class(self):
        return self.get_body_class().ratings[self.rating]

    def get_rating(self):
        """Ratings instance with translated strings attached."""
        return mkt.ratingsbodies.dehydrate_rating(self.get_rating_class())

    def get_label(self):
        """Gives us the name to be used for the form options."""
        return u'%s - %s' % (self.get_body().name, self.get_rating().name)


def update_status_content_ratings(sender, instance, **kw):
    # Flips the app's status from NULL if it has everything else together.
    if (instance.addon.has_incomplete_status() and
            instance.addon.is_fully_complete()):
        instance.addon.update(status=mkt.STATUS_PENDING)


models.signals.post_save.connect(update_status_content_ratings,
                                 sender=ContentRating,
                                 dispatch_uid='c_rating_update_app_status')


# The RatingDescriptors table is created with dynamic fields based on
# mkt.constants.ratingdescriptors.
class RatingDescriptors(ModelBase, DynamicBoolFieldsMixin):
    """
    A dynamically generated model that contains a set of boolean values
    stating if an app is rated with a particular descriptor.
    """
    addon = models.OneToOneField(Webapp, related_name='rating_descriptors')

    class Meta:
        db_table = 'webapps_rating_descriptors'

    def __unicode__(self):
        return u'%s: %s' % (self.id, self.addon.name)

    def to_keys_by_body(self, body):
        return [key for key in self.to_keys() if
                key.startswith('has_%s' % body)]

    def iarc_deserialize(self, body=None):
        """Map our descriptor strings back to the IARC ones (comma-sep.)."""
        keys = self.to_keys()
        if body:
            keys = [key for key in keys if body.iarc_name.lower() in key]
        return ', '.join(iarc_mappings.REVERSE_DESCS.get(desc) for desc
                         in keys)

# Add a dynamic field to `RatingDescriptors` model for each rating descriptor.
for db_flag, desc in mkt.iarc_mappings.REVERSE_DESCS.items():
    field = models.BooleanField(default=False, help_text=desc)
    field.contribute_to_class(RatingDescriptors, db_flag)


# The RatingInteractives table is created with dynamic fields based on
# mkt.constants.ratinginteractives.
class RatingInteractives(ModelBase, DynamicBoolFieldsMixin):
    """
    A dynamically generated model that contains a set of boolean values
    stating if an app features a particular interactive element.
    """
    addon = models.OneToOneField(Webapp, related_name='rating_interactives')

    class Meta:
        db_table = 'webapps_rating_interactives'

    def __unicode__(self):
        return u'%s: %s' % (self.id, self.addon.name)

    def iarc_deserialize(self):
        """Map our descriptor strings back to the IARC ones (comma-sep.)."""
        return ', '.join(iarc_mappings.REVERSE_INTERACTIVES.get(inter)
                         for inter in self.to_keys())


# Add a dynamic field to `RatingInteractives` model for each rating descriptor.
for interactive, db_flag in mkt.iarc_mappings.INTERACTIVES.items():
    field = models.BooleanField(default=False, help_text=interactive)
    field.contribute_to_class(RatingInteractives, db_flag)


def iarc_cleanup(*args, **kwargs):
    instance = kwargs.get('instance')
    IARCInfo.objects.filter(addon=instance).delete()
    ContentRating.objects.filter(addon=instance).delete()
    RatingDescriptors.objects.filter(addon=instance).delete()
    RatingInteractives.objects.filter(addon=instance).delete()


# When an app is deleted we need to remove the IARC data so the certificate can
# be re-used later.
models.signals.post_delete.connect(iarc_cleanup, sender=Webapp,
                                   dispatch_uid='webapps_iarc_cleanup')


# The AppFeatures table is created with dynamic fields based on
# mkt.constants.features, which requires some setup work before we call `type`.
class AppFeatures(ModelBase, DynamicBoolFieldsMixin):
    """
    A dynamically generated model that contains a set of boolean values
    stating if an app requires a particular feature.
    """
    version = models.OneToOneField(Version, related_name='features')
    field_source = APP_FEATURES

    class Meta:
        db_table = 'addons_features'

    def __unicode__(self):
        return u'Version: %s: %s' % (self.version.id, self.to_signature())

    def set_flags(self, signature):
        """
        Sets flags given the signature.

        This takes the reverse steps in `to_signature` to set the various flags
        given a signature. Boolean math is used since "0.23.1" is a valid
        signature but does not produce a string of required length when doing
        string indexing.
        """
        fields = self._fields()
        # Grab the profile part of the signature and convert to binary string.
        try:
            profile = bin(int(signature.split('.')[0], 16)).lstrip('0b')
            n = len(fields) - 1
            for i, f in enumerate(fields):
                setattr(self, f, bool(int(profile, 2) & 2 ** (n - i)))
        except ValueError as e:
            log.error(u'ValueError converting %s. %s' % (signature, e))

    def to_signature(self):
        """
        This converts the boolean values of the flags to a signature string.

        For example, all the flags in APP_FEATURES order produce a string of
        binary digits that is then converted to a hexadecimal string with the
        length of the features list plus a version appended. E.g.::

            >>> profile = '10001010111111010101011'
            >>> int(profile, 2)
            4554411
            >>> '%x' % int(profile, 2)
            '457eab'
            >>> '%x.%s.%s' % (int(profile, 2), len(profile), 1)
            '457eab.23.1'

        """
        profile = ''.join('1' if getattr(self, f) else '0'
                          for f in self._fields())
        return '%x.%s.%s' % (int(profile, 2), len(profile),
                             settings.APP_FEATURES_VERSION)

    def to_list(self):
        keys = self.to_keys()
        # Strip `has_` from each feature.
        field_names = [self.field_source[key[4:].upper()]['name']
                       for key in keys]
        return sorted(field_names)


# Add a dynamic field to `AppFeatures` model for each buchet feature.
for k, v in APP_FEATURES.iteritems():
    field = models.BooleanField(default=False, help_text=v['name'])
    field.contribute_to_class(AppFeatures, 'has_%s' % k.lower())


class AppManifest(ModelBase):
    """
    Storage for manifests.

    Tied to version since they change between versions. This stores both hosted
    and packaged apps manifests for easy access.
    """
    version = models.OneToOneField(Version, related_name='manifest_json')
    manifest = models.TextField()

    class Meta:
        db_table = 'app_manifest'


class RegionListField(JSONField):
    def to_python(self, value):
        value = super(RegionListField, self).to_python(value)
        if value:
            value = [int(v) for v in value]
        return value


class Geodata(ModelBase):
    """TODO: Forgo AER and use bool columns for every region and carrier."""
    addon = models.OneToOneField(Webapp, related_name='_geodata')
    restricted = models.BooleanField(default=False)
    popular_region = models.CharField(max_length=10, null=True)
    banner_regions = RegionListField(default=None, null=True)
    banner_message = PurifiedField()
    # Exclude apps with USK_RATING_REFUSED in Germany.
    region_de_usk_exclude = models.BooleanField(default=False)

    class Meta:
        db_table = 'webapps_geodata'

    def __unicode__(self):
        return u'%s (%s): <Webapp %s>' % (
            self.id, 'restricted' if self.restricted else 'unrestricted',
            self.addon.id)

    def get_status(self, region):
        """
        Return the status of listing in a given region (e.g., China).
        """
        return getattr(self, 'region_%s_status' % parse_region(region).slug,
                       mkt.STATUS_PUBLIC)

    def set_status(self, region, status, save=False):
        """Return a tuple of `(value, changed)`."""

        value, changed = None, False

        attr = 'region_%s_status' % parse_region(region).slug
        if hasattr(self, attr):
            value = setattr(self, attr, status)

            if self.get_status(region) != value:
                changed = True
                # Save only if the value is different.
                if save:
                    self.save()

        return None, changed

    def get_status_slug(self, region):
        return {
            mkt.STATUS_PENDING: 'pending',
            mkt.STATUS_PUBLIC: 'public',
            mkt.STATUS_REJECTED: 'rejected',
        }.get(self.get_status(region), 'unavailable')

    @classmethod
    def get_status_messages(cls):
        return {
            # L10n: An app is awaiting approval for a particular region.
            'pending': _('awaiting approval'),
            # L10n: An app is rejected for a particular region.
            'rejected': _('rejected'),
            # L10n: An app requires additional review for a particular region.
            'unavailable': _('requires additional review')
        }

    def banner_regions_names(self):
        if self.banner_regions is None:
            return []
        return sorted(unicode(mkt.regions.REGIONS_CHOICES_ID_DICT.get(k).name)
                      for k in self.banner_regions)

    def banner_regions_slugs(self):
        if self.banner_regions is None:
            return []
        return sorted(unicode(mkt.regions.REGIONS_CHOICES_ID_DICT.get(k).slug)
                      for k in self.banner_regions)

    def get_nominated_date(self, region):
        """
        Return the timestamp of when the app was approved in a region.
        """
        return getattr(self,
                       'region_%s_nominated' % parse_region(region).slug)

    def set_nominated_date(self, region, timestamp=None, save=False):
        """Return a tuple of `(value, saved)`."""

        value, changed = None, False

        attr = 'region_%s_nominated' % parse_region(region).slug
        if hasattr(self, attr):
            if timestamp is None:
                timestamp = datetime.datetime.now()
            value = setattr(self, attr, timestamp)

            if self.get_nominated_date(region) != value:
                changed = True
                # Save only if the value is different.
                if save:
                    self.save()

        return None, changed


# (1) Add a dynamic status field to `Geodata` model for each special region:
# -  0: STATUS_NULL (Unavailable)
# -  2: STATUS_PENDING (Pending)
# -  4: STATUS_PUBLIC (Public)
# - 12: STATUS_REJECTED (Rejected)
#
# (2) Add a dynamic nominated field to keep track of timestamp for when
# the developer requested approval for each region.
for region in mkt.regions.SPECIAL_REGIONS:
    help_text = _('{region} approval status').format(
        region=unicode(region.name))
    field = models.PositiveIntegerField(
        help_text=help_text,
        choices=mkt.STATUS_CHOICES.items(),
        db_index=True,
        default=mkt.STATUS_PENDING)
    field.contribute_to_class(Geodata, 'region_%s_status' % region.slug)

    help_text = _('{region} nomination date').format(
        region=unicode(region.name))
    field = models.DateTimeField(help_text=help_text, null=True)
    field.contribute_to_class(Geodata, 'region_%s_nominated' % region.slug)

# Add a dynamic field to `Geodata` model to exclude pre-IARC public unrated
# Brazil and Germany games.
for region in (mkt.regions.BRA, mkt.regions.DEU):
    field = models.BooleanField(default=False)
    field.contribute_to_class(Geodata, 'region_%s_iarc_exclude' % region.slug)

# Save geodata translations when a Geodata instance is saved.
models.signals.pre_save.connect(save_signal, sender=Geodata,
                                dispatch_uid='geodata_translations')
