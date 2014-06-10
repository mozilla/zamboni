# -*- coding: utf-8 -*-
import itertools
import os
import re
import time
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models, transaction
from django.db.models import signals as dbsignals
from django.db.models import Max, Q
from django.dispatch import receiver
from django.utils.translation import trans_real as translation

import caching.base as caching
import commonware.log
import json_field
from jinja2.filters import do_dictsort
from tower import ugettext_lazy as _

import amo
import amo.models
from addons import query, signals
from amo.decorators import use_master, write
from amo.helpers import absolutify
from amo.urlresolvers import get_outgoing_url, reverse
from amo.utils import (attach_trans_dict, find_language, send_mail, slugify,
                       sorted_groupby, timer, to_language, urlparams)
from files.models import File
from lib.utils import static_url
from mkt.ratings.models import Review
from mkt.tags.models import Tag
from translations.fields import (PurifiedField, save_signal, TranslatedField,
                                 Translation)
from users.models import UserForeignKey, UserProfile
from versions.models import Version

from mkt.access import acl
from mkt.prices.models import AddonPremium, Price


log = commonware.log.getLogger('z.addons')


def clean_slug(instance, slug_field='slug'):
    """Cleans a model instance slug.

    This strives to be as generic as possible as it's used by Addons, Webapps
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

    if BlacklistedSlug.blocked(slug):
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


class AddonManager(amo.models.ManagerBase):

    def __init__(self, include_deleted=False):
        amo.models.ManagerBase.__init__(self)
        self.include_deleted = include_deleted

    def get_query_set(self):
        qs = super(AddonManager, self).get_query_set()
        qs = qs._clone(klass=query.IndexQuerySet)
        if not self.include_deleted:
            qs = qs.exclude(status=amo.STATUS_DELETED)
        return qs.transform(Addon.transformer)

    def id_or_slug(self, val):
        if isinstance(val, basestring) and not val.isdigit():
            return self.filter(slug=val)
        return self.filter(id=val)

    def enabled(self):
        return self.filter(disabled_by_user=False)

    def public(self):
        """Get public add-ons only"""
        return self.filter(self.valid_q([amo.STATUS_PUBLIC]))

    def reviewed(self):
        """Get add-ons with a reviewed status"""
        return self.filter(self.valid_q(amo.REVIEWED_STATUSES))

    def unreviewed(self):
        """Get only unreviewed add-ons"""
        return self.filter(self.valid_q(amo.UNREVIEWED_STATUSES))

    def valid(self):
        """Get valid, enabled add-ons only"""
        return self.filter(self.valid_q(amo.LISTED_STATUSES))

    def valid_and_disabled(self):
        """
        Get valid, enabled and disabled add-ons.
        """
        statuses = list(amo.LISTED_STATUSES) + [amo.STATUS_DISABLED]
        return (self.filter(Q(status__in=statuses) | Q(disabled_by_user=True))
                .exclude(_current_version__isnull=True))

    def listed(self, app, *status):
        """
        Listed add-ons have a version with a file matching ``status`` and are
        not disabled.  Self-hosted add-ons will be returned too.
        """
        if len(status) == 0:
            status = [amo.STATUS_PUBLIC]
        return self.filter(self.valid_q(status))

    def top_free(self, app, listed=True):
        qs = self.listed(app) if listed else self
        return (qs.exclude(premium_type__in=amo.ADDON_PREMIUMS)
                .exclude(addonpremium__price__price__isnull=False)
                .order_by('-weekly_downloads')
                .with_index(addons='downloads_type_idx'))

    def top_paid(self, app, listed=True):
        qs = self.listed(app) if listed else self
        return (qs.filter(premium_type__in=amo.ADDON_PREMIUMS,
                          addonpremium__price__price__isnull=False)
                .order_by('-weekly_downloads')
                .with_index(addons='downloads_type_idx'))

    def valid_q(self, status=[], prefix=''):
        """
        Return a Q object that selects a valid Addon with the given statuses.

        An add-on is valid if not disabled and has a current version.
        ``prefix`` can be used if you're not working with Addon directly and
        need to hop across a join, e.g. ``prefix='addon__'`` in
        CollectionAddon.
        """
        if not status:
            status = [amo.STATUS_PUBLIC]

        def q(*args, **kw):
            if prefix:
                kw = dict((prefix + k, v) for k, v in kw.items())
            return Q(*args, **kw)

        return q(q(_current_version__isnull=False),
                 disabled_by_user=False, status__in=status)


class Addon(amo.models.OnChangeMixin, amo.models.ModelBase):
    STATUS_CHOICES = amo.STATUS_CHOICES.items()
    LOCALES = [(translation.to_locale(k).replace('_', '-'), v) for k, v in
               do_dictsort(settings.LANGUAGES)]

    guid = models.CharField(max_length=255, unique=True, null=True)
    slug = models.CharField(max_length=30, unique=True, null=True)
    # This column is only used for webapps, so they can have a slug namespace
    # separate from addons and personas.
    app_slug = models.CharField(max_length=30, unique=True, null=True,
                                blank=True)
    name = TranslatedField(default=None)
    default_locale = models.CharField(max_length=10,
                                      default=settings.LANGUAGE_CODE,
                                      db_column='defaultlocale')

    type = models.PositiveIntegerField(db_column='addontype_id', default=0)
    status = models.PositiveIntegerField(
        choices=STATUS_CHOICES, db_index=True, default=0)
    highest_status = models.PositiveIntegerField(
        choices=STATUS_CHOICES, default=0,
        help_text='An upper limit for what an author can change.',
        db_column='higheststatus')
    icon_type = models.CharField(max_length=25, blank=True,
                                 db_column='icontype')
    icon_hash = models.CharField(max_length=8, blank=True, null=True)
    homepage = TranslatedField()
    support_email = TranslatedField(db_column='supportemail')
    support_url = TranslatedField(db_column='supporturl')
    description = PurifiedField(short=False)

    privacy_policy = PurifiedField(db_column='privacypolicy')

    average_rating = models.FloatField(max_length=255, default=0, null=True,
                                       db_column='averagerating')
    bayesian_rating = models.FloatField(default=0, db_index=True,
                                        db_column='bayesianrating')
    total_reviews = models.PositiveIntegerField(default=0,
                                                db_column='totalreviews')
    weekly_downloads = models.PositiveIntegerField(
        default=0, db_column='weeklydownloads', db_index=True)
    total_downloads = models.PositiveIntegerField(
        default=0, db_column='totaldownloads')

    last_updated = models.DateTimeField(
        db_index=True, null=True,
        help_text='Last time this add-on had a file/version update')

    disabled_by_user = models.BooleanField(default=False, db_index=True,
                                           db_column='inactive')
    public_stats = models.BooleanField(default=False, db_column='publicstats')

    charity = models.ForeignKey('Charity', null=True)

    authors = models.ManyToManyField('users.UserProfile', through='AddonUser',
                                     related_name='addons')
    categories = models.ManyToManyField('Category', through='AddonCategory')
    premium_type = models.PositiveIntegerField(
        choices=amo.ADDON_PREMIUM_TYPES.items(), default=amo.ADDON_FREE)
    manifest_url = models.URLField(max_length=255, blank=True, null=True)
    app_domain = models.CharField(max_length=255, blank=True, null=True,
                                  db_index=True)

    _current_version = models.ForeignKey(Version, db_column='current_version',
                                         related_name='+', null=True,
                                         on_delete=models.SET_NULL)
    _latest_version = models.ForeignKey(Version, db_column='latest_version',
                                        on_delete=models.SET_NULL,
                                        null=True, related_name='+')
    make_public = models.DateTimeField(null=True)
    mozilla_contact = models.EmailField(blank=True)

    vip_app = models.BooleanField(default=False)
    priority_review = models.BooleanField(default=False)

    # Whether the app is packaged or not (aka hosted).
    is_packaged = models.BooleanField(default=False, db_index=True)

    enable_new_regions = models.BooleanField(default=False, db_index=True)

    # Annotates disabled apps from the Great IARC purge for auto-reapprove.
    # Note: for currently PUBLIC apps only.
    iarc_purged = models.BooleanField(default=False)

    # This is the public_id to a Generic Solitude Product
    solitude_public_id = models.CharField(max_length=255, null=True, blank=True)

    objects = AddonManager()
    with_deleted = AddonManager(include_deleted=True)

    class Meta:
        db_table = 'addons'

    @staticmethod
    def __new__(cls, *args, **kw):
        # Return a Webapp instead of an Addon if the `type` column says this is
        # really a webapp.
        try:
            type_idx = Addon._meta._type_idx
        except AttributeError:
            type_idx = (idx for idx, f in enumerate(Addon._meta.fields)
                        if f.attname == 'type').next()
            Addon._meta._type_idx = type_idx
        if ((len(args) == len(Addon._meta.fields) and
                args[type_idx] == amo.ADDON_WEBAPP) or kw and
                kw.get('type') == amo.ADDON_WEBAPP):
            cls = Webapp
        return object.__new__(cls)

    def __unicode__(self):
        return u'%s: %s' % (self.id, self.name)

    def save(self, **kw):
        self.clean_slug()
        super(Addon, self).save(**kw)

    @use_master
    def clean_slug(self, slug_field='slug'):
        if self.status == amo.STATUS_DELETED:
            return
        clean_slug(self, slug_field)

    @transaction.commit_on_success
    def delete(self, msg='', reason=''):
        # To avoid a circular import.
        from . import tasks
        # Check for soft deletion path. Happens only if the addon status isn't
        # 0 (STATUS_INCOMPLETE), or when we are in Marketplace.
        if self.status == amo.STATUS_DELETED:
            # We're already done.
            return

        id = self.id

        # Tell IARC this app is delisted from the set_iarc_storefront_data.
        if self.type == amo.ADDON_WEBAPP:
            self.set_iarc_storefront_data(disable=True)

        # Fetch previews before deleting the addon instance, so that we can
        # pass the list of files to delete to the delete_preview_files task
        # after the addon is deleted.
        previews = list(Preview.objects.filter(addon__id=id)
                        .values_list('id', flat=True))

        log.debug('Deleting add-on: %s' % self.id)

        to = [settings.FLIGTAR]
        user = amo.get_user()

        context = {
            'atype': amo.ADDON_TYPE.get(self.type).upper(),
            'authors': [u.email for u in self.authors.all()],
            'guid': self.guid,
            'id': self.id,
            'msg': msg,
            'reason': reason,
            'name': self.name,
            'slug': self.slug,
            'total_downloads': self.total_downloads,
            'url': absolutify(self.get_url_path()),
            'user_str': ("%s, %s (%s)" % (user.display_name or
                                          user.username, user.email,
                                          user.id) if user else "Unknown"),
        }

        email_msg = u"""
        The following %(atype)s was deleted.
        %(atype)s: %(name)s
        URL: %(url)s
        DELETED BY: %(user_str)s
        ID: %(id)s
        GUID: %(guid)s
        AUTHORS: %(authors)s
        TOTAL DOWNLOADS: %(total_downloads)s
        NOTES: %(msg)s
        REASON GIVEN BY USER FOR DELETION: %(reason)s
        """ % context
        log.debug('Sending delete email for %(atype)s %(id)s' % context)
        subject = 'Deleting %(atype)s %(slug)s (%(id)d)' % context

        # Update or NULL out various fields.
        models.signals.pre_delete.send(sender=Addon, instance=self)
        self.update(status=amo.STATUS_DELETED,
                    slug=None, app_slug=None, app_domain=None,
                    _current_version=None)
        models.signals.post_delete.send(sender=Addon, instance=self)

        send_mail(subject, email_msg, recipient_list=to)

        for preview in previews:
            tasks.delete_preview_files.delay(preview)

        return True

    @classmethod
    def from_upload(cls, upload, platforms, is_packaged=False):
        from files.utils import parse_addon

        data = parse_addon(upload)
        fields = cls._meta.get_all_field_names()
        addon = Addon(**dict((k, v) for k, v in data.items() if k in fields))
        addon.status = amo.STATUS_NULL
        locale_is_set = (addon.default_locale and
                         addon.default_locale in (
                             settings.AMO_LANGUAGES +
                             settings.HIDDEN_LANGUAGES) and
                         data.get('default_locale') == addon.default_locale)
        if not locale_is_set:
            addon.default_locale = to_language(translation.get_language())
        if addon.is_webapp():
            addon.is_packaged = is_packaged
            if is_packaged:
                addon.app_domain = data.get('origin')
            else:
                addon.manifest_url = upload.name
                addon.app_domain = addon.domain_from_url(addon.manifest_url)
        addon.save()
        Version.from_upload(upload, addon, platforms)

        amo.log(amo.LOG.CREATE_ADDON, addon)
        log.debug('New addon %r from %r' % (addon, upload))

        return addon

    def get_url_path(self, more=False, add_prefix=True):
        # If more=True you get the link to the ajax'd middle chunk of the
        # detail page.
        view = 'addons.detail_more' if more else 'addons.detail'
        return reverse(view, args=[self.slug], add_prefix=add_prefix)

    def get_api_url(self):
        # Used by Piston in output.
        return absolutify(self.get_url_path())

    def get_dev_url(self, action='edit', args=None, prefix_only=False):
        # Either link to the "new" Marketplace Developer Hub or the old one.
        args = args or []
        prefix = 'mkt.developers'
        view_name = '%s.%s' if prefix_only else '%s.apps.%s'
        return reverse(view_name % (prefix, action),
                       args=[self.app_slug] + args)

    def get_detail_url(self, action='detail', args=[]):
        return reverse('apps.%s' % action, args=[self.app_slug] + args)

    def type_url(self):
        """The url for this add-on's AddonType."""
        return AddonType(self.type).get_url_path()

    @amo.cached_property(writable=True)
    def listed_authors(self):
        return UserProfile.objects.filter(
            addons=self,
            addonuser__listed=True).order_by('addonuser__position')

    @classmethod
    def get_fallback(cls):
        return cls._meta.get_field('default_locale')

    @property
    def reviews(self):
        return Review.objects.filter(addon=self, reply_to=None)

    def language_ascii(self):
        lang = translation.to_language(self.default_locale)
        return settings.LANGUAGES.get(lang)

    @property
    def valid_file_statuses(self):
        if self.status == amo.STATUS_PUBLIC:
            return [amo.STATUS_PUBLIC]

        if self.status == amo.STATUS_PUBLIC_WAITING:
            # For public_waiting apps, accept both public and
            # public_waiting statuses, because the file status might be
            # changed from PUBLIC_WAITING to PUBLIC just before the app's
            # is.
            return amo.WEBAPPS_APPROVED_STATUSES

        if self.status in (amo.STATUS_LITE,
                           amo.STATUS_LITE_AND_NOMINATED):
            return [amo.STATUS_PUBLIC, amo.STATUS_LITE,
                    amo.STATUS_LITE_AND_NOMINATED]

        return amo.VALID_STATUSES

    def get_version(self):
        """Retrieves the latest public version of an addon."""
        try:
            status = self.valid_file_statuses

            status_list = ','.join(map(str, status))
            fltr = {'files__status__in': status}
            return self.versions.no_cache().filter(**fltr).extra(
                where=["""
                    NOT EXISTS (
                        SELECT 1 FROM versions as v2
                        INNER JOIN files AS f2 ON (f2.version_id = v2.id)
                        WHERE v2.id = versions.id
                        AND f2.status NOT IN (%s))
                    """ % status_list])[0]

        except (IndexError, Version.DoesNotExist):
            return None

    @write
    def update_version(self, ignore=None, _signal=True):
        """
        Returns true if we updated the field.

        The optional ``ignore`` parameter, if present, is a a version
        to not consider as part of the update, since it may be in the
        process of being deleted.

        Pass ``_signal=False`` if you want to no signals fired at all.

        """
        current = self.get_version()

        try:
            latest_qs = self.versions.exclude(files__status=amo.STATUS_BETA)
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
        if not self.id or self.status == amo.STATUS_DELETED:
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
        if not self.id or self.status == amo.STATUS_DELETED:
            return None
        try:
            return self._latest_version
        except ObjectDoesNotExist:
            pass
        return None

    def get_icon_dir(self):
        return os.path.join(settings.ADDON_ICONS_PATH,
                            '%s' % (self.id / 1000))

    def get_icon_url(self, size):
        """
        Returns either the icon URL or a default icon.
        """
        icon_type_split = []
        if self.icon_type:
            icon_type_split = self.icon_type.split('/')

        # Get the closest allowed size without going over.
        if (size not in amo.ADDON_ICON_SIZES
                and size >= amo.ADDON_ICON_SIZES[0]):
            size = [s for s in amo.ADDON_ICON_SIZES if s < size][-1]
        elif size < amo.ADDON_ICON_SIZES[0]:
            size = amo.ADDON_ICON_SIZES[0]

        # Figure out what to return for an image URL.
        if not self.icon_type:
            return '%s/%s-%s.png' % (static_url('ADDON_ICONS_DEFAULT_URL'),
                                     'default', size)
        elif icon_type_split[0] == 'icon':
            return '%s/%s-%s.png' % (static_url('ADDON_ICONS_DEFAULT_URL'),
                                     icon_type_split[1], size)
        else:
            # [1] is the whole ID, [2] is the directory.
            split_id = re.match(r'((\d*?)\d{1,3})$', str(self.id))
            # If we don't have the icon_hash set to a dummy string ("never"), when
            # the icon is eventually changed, icon_hash will be updated.
            suffix = getattr(self, 'icon_hash', None) or 'never'
            return static_url('ADDON_ICON_URL') % (
                split_id.group(2) or 0, self.id, size, suffix)

    @write
    def update_status(self):
        if (self.status in [amo.STATUS_NULL, amo.STATUS_DELETED]
            or self.is_disabled or self.is_webapp()):
            return

        def logit(reason, old=self.status):
            log.info('Changing add-on status [%s]: %s => %s (%s).'
                     % (self.id, old, self.status, reason))
            amo.log(amo.LOG.CHANGE_STATUS, self.get_status_display(), self)

        versions = self.versions.all()
        if not versions.exists():
            self.update(status=amo.STATUS_NULL)
            logit('no versions')
        elif not (versions.filter(files__isnull=False).exists()):
            self.update(status=amo.STATUS_NULL)
            logit('no versions with files')
        elif (self.status == amo.STATUS_PUBLIC and
              not versions.filter(files__status=amo.STATUS_PUBLIC).exists()):
            if versions.filter(files__status=amo.STATUS_LITE).exists():
                self.update(status=amo.STATUS_LITE)
                logit('only lite files')
            else:
                self.update(status=amo.STATUS_UNREVIEWED)
                logit('no reviewed files')

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

    @staticmethod
    def attach_listed_authors(addons, addon_dict=None):
        if addon_dict is None:
            addon_dict = dict((a.id, a) for a in addons)

        q = (UserProfile.objects.no_cache()
             .filter(addons__in=addons, addonuser__listed=True)
             .extra(select={'addon_id': 'addons_users.addon_id',
                            'position': 'addons_users.position'}))
        q = sorted(q, key=lambda u: (u.addon_id, u.position))
        for addon_id, users in itertools.groupby(q, key=lambda u: u.addon_id):
            addon_dict[addon_id].listed_authors = list(users)
        # FIXME: set listed_authors to empty list on addons without listed
        # authors.

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
    def attach_prices(addons, addon_dict=None):
        # FIXME: merge with attach_prices transformer below.
        if addon_dict is None:
            addon_dict = dict((a.id, a) for a in addons)

        # There's a constrained amount of price tiers, may as well load
        # them all and let cache machine keep them cached.
        prices = dict((p.id, p) for p in Price.objects.all())
        # Attach premium addons.
        qs = AddonPremium.objects.filter(addon__in=addons)
        premium_dict = dict((ap.addon_id, ap) for ap in qs)

        # Attach premiums to addons, making sure to attach None to free addons
        # or addons where the corresponding AddonPremium is missing.
        for addon in addons:
            if addon.is_premium():
                addon_p = premium_dict.get(addon.id)
                if addon_p:
                    price = prices.get(addon_p.price_id)
                    if price:
                        addon_p.price = price
                    addon_p.addon = addon
                addon._premium = addon_p
            else:
                addon._premium = None

    @staticmethod
    @timer
    def transformer(addons):
        if not addons:
            return

        addon_dict = dict((a.id, a) for a in addons)
        addons = [a for a in addons if a.type != amo.ADDON_PERSONA]

        # Set _latest_version and _current_version.
        Addon.attach_related_versions(addons, addon_dict=addon_dict)

        # Attach listed authors.
        Addon.attach_listed_authors(addons, addon_dict=addon_dict)

        # Attach previews.
        Addon.attach_previews(addons, addon_dict=addon_dict)

        # Attach prices.
        Addon.attach_prices(addons, addon_dict=addon_dict)

        return addon_dict

    @property
    def show_beta(self):
        return self.status == amo.STATUS_PUBLIC and self.current_beta_version

    @amo.cached_property
    def current_beta_version(self):
        """Retrieves the latest version of an addon, in the beta channel."""
        versions = self.versions.filter(files__status=amo.STATUS_BETA)[:1]

        if versions:
            return versions[0]

    @property
    def icon_url(self):
        return self.get_icon_url(32)

    def authors_other_addons(self, app=None):
        """
        Return other addons by the author(s) of this addon,
        optionally takes an app.
        """
        if app:
            qs = Addon.objects.listed(app)
        else:
            qs = Addon.objects.valid()
        return (qs.exclude(id=self.id)
                  .exclude(type=amo.ADDON_WEBAPP)
                  .filter(addonuser__listed=True,
                          authors__in=self.listed_authors)
                  .distinct())

    @property
    def thumbnail_url(self):
        """
        Returns the addon's thumbnail url or a default.
        """
        try:
            preview = self.all_previews[0]
            return preview.thumbnail_url
        except IndexError:
            return settings.MEDIA_URL + '/img/icons/no-preview.png'

    def can_request_review(self):
        """Return the statuses an add-on can request."""
        if not File.objects.filter(version__addon=self):
            return ()
        if (self.is_disabled or
            self.status in (amo.STATUS_PUBLIC,
                            amo.STATUS_LITE_AND_NOMINATED,
                            amo.STATUS_DELETED) or
            not self.latest_version or
            not self.latest_version.files.exclude(status=amo.STATUS_DISABLED)):
            return ()
        elif self.status == amo.STATUS_NOMINATED:
            return (amo.STATUS_LITE,)
        elif self.status == amo.STATUS_UNREVIEWED:
            return (amo.STATUS_PUBLIC,)
        elif self.status == amo.STATUS_LITE:
            if self.days_until_full_nomination() == 0:
                return (amo.STATUS_PUBLIC,)
            else:
                # Still in preliminary waiting period...
                return ()
        else:
            return (amo.STATUS_LITE, amo.STATUS_PUBLIC)

    def days_until_full_nomination(self):
        """Returns number of days until author can request full review.

        If wait period is over or this doesn't apply at all, returns 0 days.
        An author must wait 10 days after submitting first LITE approval
        to request FULL.
        """
        if self.status != amo.STATUS_LITE:
            return 0
        # Calculate wait time from the earliest submitted version:
        qs = (File.objects.filter(version__addon=self, status=self.status)
              .order_by('created').values_list('datestatuschanged'))[:1]
        if qs:
            days_ago = datetime.now() - qs[0][0]
            if days_ago < timedelta(days=10):
                return 10 - days_ago.days
        return 0

    def is_webapp(self):
        return self.type == amo.ADDON_WEBAPP

    @property
    def is_disabled(self):
        """True if this Addon is disabled.

        It could be disabled by an admin or disabled by the developer
        """
        return self.status == amo.STATUS_DISABLED or self.disabled_by_user

    @property
    def is_deleted(self):
        return self.status == amo.STATUS_DELETED

    @property
    def is_under_review(self):
        return self.status in amo.STATUS_UNDER_REVIEW

    def is_unreviewed(self):
        return self.status in amo.UNREVIEWED_STATUSES

    def is_public(self):
        return self.status == amo.STATUS_PUBLIC and not self.disabled_by_user

    def is_public_waiting(self):
        return self.status == amo.STATUS_PUBLIC_WAITING

    def is_incomplete(self):
        return self.status == amo.STATUS_NULL

    def is_pending(self):
        return self.status == amo.STATUS_PENDING

    def is_rejected(self):
        return self.status == amo.STATUS_REJECTED

    def can_become_premium(self):
        """
        Not all addons can become premium and those that can only at
        certain times. Webapps can become premium at any time.
        """
        if self.upsell:
            return False
        if self.type == amo.ADDON_WEBAPP and not self.is_premium():
            return True
        return (self.status in amo.PREMIUM_STATUSES
                and self.highest_status in amo.PREMIUM_STATUSES
                and self.type in amo.ADDON_BECOME_PREMIUM)

    def is_premium(self):
        """
        If the addon is premium. Will include addons that are premium
        and have a price of zero. Primarily of use in the devhub to determine
        if an app is intending to be premium.
        """
        return self.premium_type in amo.ADDON_PREMIUMS

    def is_free(self):
        """
        This is the opposite of is_premium. Will not include apps that have a
        price of zero. Primarily of use in the devhub to determine if an app is
        intending to be free.
        """
        return not (self.is_premium() and self.premium and
                    self.premium.price)

    def is_free_inapp(self):
        return self.premium_type == amo.ADDON_FREE_INAPP

    def needs_payment(self):
        return (self.premium_type not in
                (amo.ADDON_FREE, amo.ADDON_OTHER_INAPP))

    def can_be_deleted(self):
        return not self.is_deleted

    @amo.cached_property
    def tags_partitioned_by_developer(self):
        """Returns a tuple of developer tags and user tags for this addon."""
        tags = self.tags.not_blacklisted()
        user_tags = tags.exclude(addon_tags__user__in=self.listed_authors)
        dev_tags = tags.exclude(id__in=[t.id for t in user_tags])
        return dev_tags, user_tags

    def has_author(self, user, roles=None):
        """True if ``user`` is an author with any of the specified ``roles``.

        ``roles`` should be a list of valid roles (see amo.AUTHOR_ROLE_*). If
        not specified, has_author will return true if the user has any role.
        """
        if user is None or user.is_anonymous():
            return False
        if roles is None:
            roles = dict(amo.AUTHOR_CHOICES).keys()
        return AddonUser.objects.filter(addon=self, user=user,
                                        role__in=roles).exists()

    @classmethod
    def _last_updated_queries(cls):
        """
        Get the queries used to calculate addon.last_updated.
        """
        status_change = Max('versions__files__datestatuschanged')
        public = (
            Addon.objects.no_cache().filter(
                status=amo.STATUS_PUBLIC,
                versions__files__status=amo.STATUS_PUBLIC)
            .exclude(type__in=(amo.ADDON_PERSONA, amo.ADDON_WEBAPP))
            .values('id').annotate(last_updated=status_change))

        lite = (
            Addon.objects.no_cache().filter(
                status__in=amo.LISTED_STATUSES,
                versions__files__status=amo.STATUS_LITE)
            .exclude(type=amo.ADDON_WEBAPP)
            .values('id').annotate(last_updated=status_change))

        stati = amo.LISTED_STATUSES + (amo.STATUS_PUBLIC,)
        exp = (Addon.objects.no_cache().exclude(status__in=stati)
               .filter(versions__files__status__in=amo.VALID_STATUSES)
               .exclude(type=amo.ADDON_WEBAPP)
               .values('id')
               .annotate(last_updated=Max('versions__files__created')))

        webapps = (Addon.objects.no_cache()
                   .filter(type=amo.ADDON_WEBAPP,
                           status=amo.STATUS_PUBLIC,
                           versions__files__status=amo.STATUS_PUBLIC)
                   .values('id')
                   .annotate(last_updated=Max('versions__created')))

        return dict(public=public, exp=exp, lite=lite, webapps=webapps)

    @amo.cached_property(writable=True)
    def all_categories(self):
        return list(self.categories.all())

    @amo.cached_property(writable=True)
    def all_previews(self):
        return list(self.get_previews())

    def get_previews(self):
        """Exclude promo graphics."""
        return self.previews.exclude(position=-1)

    def remove_locale(self, locale):
        """NULLify strings in this locale for the add-on and versions."""
        for o in itertools.chain([self], self.versions.all()):
            Translation.objects.remove_for(o, locale)

    def get_localepicker(self):
        """For language packs, gets the contents of localepicker."""
        if (self.type == amo.ADDON_LPAPP and self.status == amo.STATUS_PUBLIC
            and self.current_version):
            files = (self.current_version.files
                         .filter(platform__in=amo.MOBILE_PLATFORMS.keys()))
            try:
                return unicode(files[0].get_localepicker(), 'utf-8')
            except IndexError:
                pass
        return ''

    def get_mozilla_contacts(self):
        return [x.strip() for x in self.mozilla_contact.split(',')]

    @amo.cached_property
    def upsell(self):
        """Return the upsell or add-on, or None if there isn't one."""
        try:
            # We set unique_together on the model, so there will only be one.
            return self._upsell_from.all()[0]
        except IndexError:
            pass

    @amo.cached_property
    def upsold(self):
        """
        Return what this is going to upsold from,
        or None if there isn't one.
        """
        try:
            return self._upsell_to.all()[0]
        except IndexError:
            pass

    def get_purchase_type(self, user):
        if user and isinstance(user, UserProfile):
            try:
                return self.addonpurchase_set.get(user=user).type
            except models.ObjectDoesNotExist:
                pass

    def has_purchased(self, user):
        return self.get_purchase_type(user) == amo.CONTRIB_PURCHASE

    def is_refunded(self, user):
        return self.get_purchase_type(user) == amo.CONTRIB_REFUND

    def is_chargeback(self, user):
        return self.get_purchase_type(user) == amo.CONTRIB_CHARGEBACK

    def can_review(self, user):
        if user and self.has_author(user):
            return False
        else:
            return (not self.is_premium() or self.has_purchased(user) or
                    self.is_refunded(user))

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

    def in_rereview_queue(self):
        # Rereview is part of marketplace and not AMO, so setting for False
        # to avoid having to catch NotImplemented errors.
        return False

    def sign_if_packaged(self, version_pk, reviewer=False):
        raise NotImplementedError('Not available for add-ons.')

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
    def app_type(self):
        # Not implemented for non-webapps.
        return ''

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

dbsignals.pre_save.connect(save_signal, sender=Addon,
                           dispatch_uid='addon_translations')


class AddonDeviceType(amo.models.ModelBase):
    addon = models.ForeignKey(Addon, db_constraint=False)
    device_type = models.PositiveIntegerField(
        default=amo.DEVICE_DESKTOP, choices=do_dictsort(amo.DEVICE_TYPES),
        db_index=True)

    class Meta:
        db_table = 'addons_devicetypes'
        unique_together = ('addon', 'device_type')

    def __unicode__(self):
        return u'%s: %s' % (self.addon.name, self.device.name)

    @property
    def device(self):
        return amo.DEVICE_TYPES[self.device_type]


@receiver(signals.version_changed, dispatch_uid='version_changed')
def version_changed(sender, **kw):
    from . import tasks
    tasks.version_changed.delay(sender.id)


@Addon.on_change
def watch_status(old_attr={}, new_attr={}, instance=None,
                 sender=None, **kw):
    """Set nomination date if self.status asks for full review.

    The nomination date will only be set when the status of the addon changes.
    The nomination date cannot be reset, say, when a developer cancels their
    request for full review and re-requests full review.

    If a version is rejected after nomination, the developer has to upload a
    new version.
    """
    new_status = new_attr.get('status')
    if not new_status:
        return
    addon = instance
    stati = (amo.STATUS_NOMINATED, amo.STATUS_LITE_AND_NOMINATED)
    if new_status in stati and old_attr['status'] != new_status:
        try:
            latest = addon.versions.latest()
            if not latest.nomination:
                latest.update(nomination=datetime.now())
        except Version.DoesNotExist:
            pass


@Addon.on_change
def watch_disabled(old_attr={}, new_attr={}, instance=None, sender=None, **kw):
    attrs = dict((k, v) for k, v in old_attr.items()
                 if k in ('disabled_by_user', 'status'))
    if Addon(**attrs).is_disabled and not instance.is_disabled:
        for f in File.objects.filter(version__addon=instance.id):
            f.unhide_disabled_file()
    if instance.is_disabled and not Addon(**attrs).is_disabled:
        for f in File.objects.filter(version__addon=instance.id):
            f.hide_disabled_file()


def attach_devices(addons):
    addon_dict = dict((a.id, a) for a in addons if a.type == amo.ADDON_WEBAPP)
    devices = (AddonDeviceType.objects.filter(addon__in=addon_dict)
               .values_list('addon', 'device_type'))
    for addon, device_types in sorted_groupby(devices, lambda x: x[0]):
        addon_dict[addon].device_ids = [d[1] for d in device_types]


def attach_prices(addons):
    addon_dict = dict((a.id, a) for a in addons)
    prices = (AddonPremium.objects
              .filter(addon__in=addon_dict,
                      addon__premium_type__in=amo.ADDON_PREMIUMS)
              .values_list('addon', 'price__price'))
    for addon, price in prices:
        addon_dict[addon].price = price


def attach_categories(addons):
    """Put all of the add-on's categories into a category_ids list."""
    addon_dict = dict((a.id, a) for a in addons)
    categories = (Category.objects.filter(addoncategory__addon__in=addon_dict)
                  .values_list('addoncategory__addon', 'id'))
    for addon, cats in sorted_groupby(categories, lambda x: x[0]):
        addon_dict[addon].category_ids = [c[1] for c in cats]


def attach_translations(addons):
    """Put all translations into a translations dict."""
    attach_trans_dict(Addon, addons)


def attach_tags(addons):
    addon_dict = dict((a.id, a) for a in addons)
    qs = (Tag.objects.not_blacklisted().filter(addons__in=addon_dict)
          .values_list('addons__id', 'tag_text'))
    for addon, tags in sorted_groupby(qs, lambda x: x[0]):
        addon_dict[addon].tag_list = [t[1] for t in tags]


class AddonCategory(caching.CachingMixin, models.Model):
    addon = models.ForeignKey(Addon)
    category = models.ForeignKey('Category')
    feature = models.BooleanField(default=False)
    feature_locales = models.CharField(max_length=255, default='', null=True)

    objects = caching.CachingManager()

    class Meta:
        db_table = 'addons_categories'
        unique_together = ('addon', 'category')


class AddonType(amo.models.ModelBase):
    name = TranslatedField()
    name_plural = TranslatedField()
    description = TranslatedField()

    class Meta:
        db_table = 'addontypes'

    def __unicode__(self):
        return unicode(self.name)

    def get_url_path(self):
        try:
            type = amo.ADDON_SLUGS[self.id]
        except KeyError:
            return None
        return reverse('browse.%s' % type)

dbsignals.pre_save.connect(save_signal, sender=AddonType,
                           dispatch_uid='addontype_translations')


class AddonUser(caching.CachingMixin, models.Model):
    addon = models.ForeignKey(Addon)
    user = UserForeignKey()
    role = models.SmallIntegerField(default=amo.AUTHOR_ROLE_OWNER,
                                    choices=amo.AUTHOR_CHOICES)
    listed = models.BooleanField(_(u'Listed'), default=True)
    position = models.IntegerField(default=0)

    objects = caching.CachingManager()

    def __init__(self, *args, **kwargs):
        super(AddonUser, self).__init__(*args, **kwargs)
        self._original_role = self.role
        self._original_user_id = self.user_id

    class Meta:
        db_table = 'addons_users'


class Category(amo.models.OnChangeMixin, amo.models.ModelBase):
    name = TranslatedField()
    slug = amo.models.SlugField(max_length=50,
                                help_text='Used in Category URLs.')
    type = models.PositiveIntegerField(db_column='addontype_id',
                                       choices=do_dictsort(amo.ADDON_TYPE))
    count = models.IntegerField('Addon count', default=0)
    weight = models.IntegerField(
        default=0, help_text='Category weight used in sort ordering')
    misc = models.BooleanField(default=False)

    addons = models.ManyToManyField(Addon, through='AddonCategory')

    class Meta:
        db_table = 'categories'
        verbose_name_plural = 'Categories'

    def __unicode__(self):
        return unicode(self.name)

    def get_url_path(self):
        return '/search?cat=%s' % self.slug

    @staticmethod
    def transformer(addons):
        qs = (Category.objects.no_cache().filter(addons__in=addons)
              .extra(select={'addon_id': 'addons_categories.addon_id'}))
        cats = dict((addon_id, list(cs))
                    for addon_id, cs in sorted_groupby(qs, 'addon_id'))
        for addon in addons:
            addon.all_categories = cats.get(addon.id, [])

    def clean(self):
        if self.slug.isdigit():
            raise ValidationError('Slugs cannot be all numbers.')


@Category.on_change
def reindex_cat_slug(old_attr=None, new_attr=None, instance=None,
                     sender=None, **kw):
    """ES reindex category's apps if category slug changes."""
    from mkt.webapps.tasks import index_webapps

    if new_attr.get('type') != amo.ADDON_WEBAPP:
        instance.save()
        return

    slug_changed = (instance.pk is not None and old_attr and new_attr and
                    old_attr.get('slug') != new_attr.get('slug'))

    instance.save()

    if slug_changed:
        index_webapps(list(instance.addon_set.filter(type=amo.ADDON_WEBAPP)
                           .values_list('id', flat=True)))


dbsignals.pre_save.connect(save_signal, sender=Category,
                           dispatch_uid='category_translations')


class Preview(amo.models.ModelBase):
    addon = models.ForeignKey(Addon, related_name='previews')
    filetype = models.CharField(max_length=25)
    thumbtype = models.CharField(max_length=25)
    caption = TranslatedField()

    position = models.IntegerField(default=0)
    sizes = json_field.JSONField(max_length=25, default={})

    class Meta:
        db_table = 'previews'
        ordering = ('position', 'created')

    def _image_url(self, url_template):
        if self.modified is not None:
            modified = int(time.mktime(self.modified.timetuple()))
        else:
            modified = 0
        args = [self.id / 1000, self.id, modified]
        if '.png' not in url_template:
            args.insert(2, self.file_extension)
        return url_template % tuple(args)

    def _image_path(self, url_template):
        args = [self.id / 1000, self.id]
        if '.png' not in url_template:
            args.append(self.file_extension)
        return url_template % tuple(args)

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
        return self._image_url(static_url('PREVIEW_THUMBNAIL_URL'))

    @property
    def image_url(self):
        return self._image_url(static_url('PREVIEW_FULL_URL'))

    @property
    def thumbnail_path(self):
        return self._image_path(settings.PREVIEW_THUMBNAIL_PATH)

    @property
    def image_path(self):
        return self._image_path(settings.PREVIEW_FULL_PATH)

    @property
    def thumbnail_size(self):
        return self.sizes.get('thumbnail', []) if self.sizes else []

    @property
    def image_size(self):
        return self.sizes.get('image', []) if self.sizes else []

dbsignals.pre_save.connect(save_signal, sender=Preview,
                           dispatch_uid='preview_translations')


class Charity(amo.models.ModelBase):
    name = models.CharField(max_length=255)
    url = models.URLField()
    paypal = models.CharField(max_length=255)

    class Meta:
        db_table = 'charities'

    @property
    def outgoing_url(self):
        if self.pk == amo.FOUNDATION_ORG:
            return self.url
        return get_outgoing_url(unicode(self.url))


class BlacklistedSlug(amo.models.ModelBase):
    name = models.CharField(max_length=255, unique=True, default='')

    class Meta:
        db_table = 'addons_blacklistedslug'

    def __unicode__(self):
        return self.name

    @classmethod
    def blocked(cls, slug):
        return slug.isdigit() or cls.objects.filter(name=slug).exists()


class AddonUpsell(amo.models.ModelBase):
    free = models.ForeignKey(Addon, related_name='_upsell_from')
    premium = models.ForeignKey(Addon, related_name='_upsell_to')

    class Meta:
        db_table = 'addon_upsell'
        unique_together = ('free', 'premium')

    def __unicode__(self):
        return u'Free: %s to Premium: %s' % (self.free, self.premium)

    @amo.cached_property
    def premium_addon(self):
        """
        Return the premium version, or None if there isn't one.
        """
        try:
            return self.premium
        except Addon.DoesNotExist:
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

dbsignals.post_delete.connect(cleanup_upsell, sender=Addon,
                              dispatch_uid='addon_upsell')


# webapps.models imports addons.models to get Addon, so we need to keep the
# Webapp import down here.
from mkt.webapps.models import Webapp
