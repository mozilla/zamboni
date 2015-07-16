import imghdr
import json
import os.path
import posixpath
import string
import uuid
from copy import copy
from datetime import datetime

from django.apps import apps
from django.conf import settings
from django.core.urlresolvers import reverse
from django.db import models
from django.utils.safestring import mark_safe

import bleach
import commonware.log
import jinja2
from tower import ugettext as _

import mkt
from lib.crypto import generate_key
from lib.pay_server import client
from mkt.access.models import Group
from mkt.constants.payments import ACCESS_SIMULATE
from mkt.constants.payments import PROVIDER_BANGO, PROVIDER_CHOICES
from mkt.ratings.models import Review
from mkt.site.models import ManagerBase, ModelBase
from mkt.tags.models import Tag
from mkt.users.models import UserForeignKey, UserProfile
from mkt.versions.models import Version
from mkt.webapps.models import Webapp
from mkt.websites.models import Website


log = commonware.log.getLogger('z.devhub')


class CantCancel(Exception):
    pass


class SolitudeSeller(ModelBase):
    # TODO: When Solitude allows for it, this should be updated to be 1:1 with
    # users.
    user = UserForeignKey()
    uuid = models.CharField(max_length=255, unique=True)
    resource_uri = models.CharField(max_length=255)

    class Meta:
        db_table = 'payments_seller'

    @classmethod
    def create(cls, user):
        uuid_ = str(uuid.uuid4())
        res = client.api.generic.seller.post(data={'uuid': uuid_})
        uri = res['resource_uri']
        obj = cls.objects.create(user=user, uuid=uuid_, resource_uri=uri)

        log.info('[User:%s] Created Solitude seller (uuid:%s)' %
                 (user, uuid_))
        return obj


class PaymentAccount(ModelBase):
    user = UserForeignKey()
    name = models.CharField(max_length=64)
    agreed_tos = models.BooleanField(default=False)
    solitude_seller = models.ForeignKey(SolitudeSeller)

    # These two fields can go away when we're not 1:1 with SolitudeSellers.
    seller_uri = models.CharField(max_length=255, unique=True)
    uri = models.CharField(max_length=255, unique=True)
    # A soft-delete so we can talk to Solitude asynchronously.
    inactive = models.BooleanField(default=False)
    # The id for this account from the provider.
    account_id = models.CharField(max_length=255)
    # Each account will be for a particular provider.
    provider = models.IntegerField(choices=PROVIDER_CHOICES,
                                   default=PROVIDER_BANGO)
    shared = models.BooleanField(default=False)

    class Meta:
        db_table = 'payment_accounts'
        unique_together = ('user', 'uri')

    def cancel(self, disable_refs=False):
        """Cancels the payment account.

        If `disable_refs` is set, existing apps that use this payment account
        will be set to STATUS_NULL.

        """
        account_refs = AddonPaymentAccount.objects.filter(account_uri=self.uri)
        if self.shared and account_refs:
            # With sharing a payment account comes great responsibility. It
            # would be really mean to create a payment account, share it
            # and have lots of apps use it. Then one day you remove it and
            # make a whole pile of apps in the marketplace get removed from
            # the store, or have in-app payments fail.
            #
            # For the moment I'm just stopping this completely, if this ever
            # happens, we'll have to go through a deprecation phase.
            # - let all the apps that use it know
            # - when they have all stopped sharing it
            # - re-run this
            log.error('Cannot cancel a shared payment account that has '
                      'apps using it.')
            raise CantCancel('You cannot cancel a shared payment account.')

        self.update(inactive=True)
        log.info('Soft-deleted payment account (uri: %s)' % self.uri)

        for acc_ref in account_refs:
            if (disable_refs and
                    not acc_ref.addon.has_multiple_payment_accounts()):
                log.info('Changing app status to NULL for app: {0}'
                         'because of payment account deletion'.format(
                             acc_ref.addon_id))

                acc_ref.addon.update(status=mkt.STATUS_NULL)
            log.info('Deleting AddonPaymentAccount for app: {0} because of '
                     'payment account deletion'.format(acc_ref.addon_id))
            acc_ref.delete()

    def get_provider(self):
        """Returns an instance of the payment provider for this account."""
        # TODO: fix circular import. Providers imports models which imports
        # forms which imports models.
        from mkt.developers.providers import get_provider
        return get_provider(id=self.provider)

    def __unicode__(self):
        date = self.created.strftime('%m/%y')
        if not self.shared:
            return u'%s - %s' % (date, self.name)
        # L10n: {0} is the name of the account.
        return _(u'Donate to {0}'.format(self.name))

    def get_agreement_url(self):
        return reverse('mkt.developers.provider.agreement', args=[self.pk])


class AddonPaymentAccount(ModelBase):
    addon = models.ForeignKey(
        'webapps.Webapp', related_name='app_payment_accounts')
    payment_account = models.ForeignKey(PaymentAccount)
    account_uri = models.CharField(max_length=255)
    product_uri = models.CharField(max_length=255, unique=True)

    class Meta:
        db_table = 'addon_payment_account'

    @property
    def user(self):
        return self.payment_account.user


class UserInappKey(ModelBase):
    solitude_seller = models.ForeignKey(SolitudeSeller)
    seller_product_pk = models.IntegerField(unique=True)

    def secret(self):
        return self._product().get()['secret']

    def public_id(self):
        return self._product().get()['public_id']

    def reset(self):
        self._product().patch(data={'secret': generate_key(48)})

    @classmethod
    def create(cls, user, secret=None):
        if secret is None:
            secret = generate_key(48)
        sel = SolitudeSeller.create(user)
        # Create a product key that can only be used for simulated purchases.
        prod = client.api.generic.product.post(data={
            'seller': sel.resource_uri, 'secret': secret,
            'external_id': str(uuid.uuid4()), 'public_id': str(uuid.uuid4()),
            'access': ACCESS_SIMULATE,
        })
        log.info(u'User %s created an in-app payments dev key product=%s '
                 u'with %s' % (unicode(user), prod['resource_pk'], sel))
        return cls.objects.create(solitude_seller=sel,
                                  seller_product_pk=prod['resource_pk'])

    def _product(self):
        return client.api.generic.product(self.seller_product_pk)

    class Meta:
        db_table = 'user_inapp_keys'


class PreloadTestPlan(ModelBase):
    addon = models.ForeignKey('webapps.Webapp')
    last_submission = models.DateTimeField(auto_now_add=True)
    filename = models.CharField(max_length=60)
    status = models.PositiveSmallIntegerField(default=mkt.STATUS_PUBLIC)

    class Meta:
        db_table = 'preload_test_plans'
        ordering = ['-last_submission']

    @property
    def preload_test_plan_url(self):
        host = (settings.PRIVATE_MIRROR_URL if self.addon.is_disabled
                else settings.LOCAL_MIRROR_URL)
        return posixpath.join(host, str(self.addon.id), self.filename)


# When an app is deleted we need to remove the preload test plan.
def preload_cleanup(*args, **kwargs):
    instance = kwargs.get('instance')
    PreloadTestPlan.objects.filter(addon=instance).delete()


models.signals.post_delete.connect(preload_cleanup, sender=Webapp,
                                   dispatch_uid='webapps_preload_cleanup')


class AppLog(ModelBase):
    """
    This table is for indexing the activity log by app.
    """
    addon = models.ForeignKey('webapps.Webapp', db_constraint=False)
    activity_log = models.ForeignKey('ActivityLog')

    class Meta:
        db_table = 'log_activity_app'
        ordering = ('-created',)


class CommentLog(ModelBase):
    """
    This table is for indexing the activity log by comment.
    """
    activity_log = models.ForeignKey('ActivityLog')
    comments = models.CharField(max_length=255)

    class Meta:
        db_table = 'log_activity_comment'
        ordering = ('-created',)


class VersionLog(ModelBase):
    """
    This table is for indexing the activity log by version.
    """
    activity_log = models.ForeignKey('ActivityLog')
    version = models.ForeignKey(Version)

    class Meta:
        db_table = 'log_activity_version'
        ordering = ('-created',)


class UserLog(ModelBase):
    """
    This table is for indexing the activity log by user.
    Note: This includes activity performed unto the user.
    """
    activity_log = models.ForeignKey('ActivityLog')
    user = models.ForeignKey(UserProfile)

    class Meta:
        db_table = 'log_activity_user'
        ordering = ('-created',)


class GroupLog(ModelBase):
    """
    This table is for indexing the activity log by access group.
    """
    activity_log = models.ForeignKey('ActivityLog')
    group = models.ForeignKey(Group)

    class Meta:
        db_table = 'log_activity_group'
        ordering = ('-created',)


class ActivityLogManager(ManagerBase):

    def for_apps(self, apps):
        vals = (AppLog.objects.filter(addon__in=apps)
                .values_list('activity_log', flat=True))

        if vals:
            return self.filter(pk__in=list(vals))
        else:
            return self.none()

    def for_version(self, version):
        vals = (VersionLog.objects.filter(version=version)
                .values_list('activity_log', flat=True))
        return self.filter(pk__in=list(vals))

    def for_group(self, group):
        return self.filter(grouplog__group=group)

    def for_user(self, user):
        vals = (UserLog.objects.filter(user=user)
                .values_list('activity_log', flat=True))
        return self.filter(pk__in=list(vals))

    def for_developer(self):
        return self.exclude(action__in=mkt.LOG_ADMINS + mkt.LOG_HIDE_DEVELOPER)

    def admin_events(self):
        return self.filter(action__in=mkt.LOG_ADMINS)

    def editor_events(self):
        return self.filter(action__in=mkt.LOG_EDITORS)

    def review_queue(self, webapp=False):
        qs = self._by_type(webapp)
        return (qs.filter(action__in=mkt.LOG_REVIEW_QUEUE)
                  .exclude(user__id=settings.TASK_USER_ID))

    def total_reviews(self, webapp=False):
        qs = self._by_type(webapp)
        """Return the top users, and their # of reviews."""
        return (qs.values('user', 'user__display_name', 'user__email')
                  .filter(action__in=mkt.LOG_REVIEW_QUEUE)
                  .exclude(user__id=settings.TASK_USER_ID)
                  .annotate(approval_count=models.Count('id'))
                  .order_by('-approval_count'))

    def monthly_reviews(self, webapp=False):
        """Return the top users for the month, and their # of reviews."""
        qs = self._by_type(webapp)
        now = datetime.now()
        created_date = datetime(now.year, now.month, 1)
        return (qs.values('user', 'user__display_name', 'user__email')
                  .filter(created__gte=created_date,
                          action__in=mkt.LOG_REVIEW_QUEUE)
                  .exclude(user__id=settings.TASK_USER_ID)
                  .annotate(approval_count=models.Count('id'))
                  .order_by('-approval_count'))

    def user_position(self, values_qs, user):
        try:
            return next(i for (i, d) in enumerate(list(values_qs))
                        if d.get('user') == user.id) + 1
        except StopIteration:
            return None

    def total_reviews_user_position(self, user, webapp=False):
        return self.user_position(self.total_reviews(webapp), user)

    def monthly_reviews_user_position(self, user, webapp=False):
        return self.user_position(self.monthly_reviews(webapp), user)

    def _by_type(self, webapp=False):
        qs = super(ActivityLogManager, self).get_queryset()
        return qs.extra(
            tables=['log_activity_app'],
            where=['log_activity_app.activity_log_id=log_activity.id'])


class SafeFormatter(string.Formatter):
    """A replacement for str.format that escapes interpolated values."""

    def get_field(self, *args, **kw):
        # obj is the value getting interpolated into the string.
        obj, used_key = super(SafeFormatter, self).get_field(*args, **kw)
        return jinja2.escape(obj), used_key


class ActivityLog(ModelBase):
    TYPES = sorted([(value.id, key) for key, value in mkt.LOG.items()])
    user = models.ForeignKey('users.UserProfile', null=True)
    action = models.SmallIntegerField(choices=TYPES, db_index=True)
    _arguments = models.TextField(blank=True, db_column='arguments')
    _details = models.TextField(blank=True, db_column='details')
    objects = ActivityLogManager()

    formatter = SafeFormatter()

    class Meta:
        db_table = 'log_activity'
        ordering = ('-created',)

    def f(self, *args, **kw):
        """Calls SafeFormatter.format and returns a Markup string."""
        # SafeFormatter escapes everything so this is safe.
        return jinja2.Markup(self.formatter.format(*args, **kw))

    @property
    def arguments(self):

        try:
            # d is a structure:
            # ``d = [{'addons.addon':12}, {'addons.addon':1}, ... ]``
            d = json.loads(self._arguments)
        except:
            log.debug('unserializing data from addon_log failed: %s' % self.id)
            return None

        objs = []
        for item in d:
            # item has only one element.
            model_name, pk = item.items()[0]
            if model_name in ('str', 'int', 'null'):
                objs.append(pk)
            else:
                (app_label, model_name) = model_name.split('.')
                model = apps.get_model(app_label, model_name)
                # Cope with soft deleted models.
                if hasattr(model, 'with_deleted'):
                    objs.extend(model.with_deleted.filter(pk=pk))
                else:
                    objs.extend(model.objects.filter(pk=pk))

        return objs

    @arguments.setter
    def arguments(self, args=[]):
        """
        Takes an object or a tuple of objects and serializes them and stores it
        in the db as a json string.
        """
        if args is None:
            args = []

        if not isinstance(args, (list, tuple)):
            args = (args,)

        serialize_me = []

        for arg in args:
            if isinstance(arg, basestring):
                serialize_me.append({'str': arg})
            elif isinstance(arg, (int, long)):
                serialize_me.append({'int': arg})
            elif isinstance(arg, tuple):
                # Instead of passing an addon instance you can pass a tuple:
                # (Webapp, 3) for Webapp with pk=3
                serialize_me.append(dict(((unicode(arg[0]._meta), arg[1]),)))
            elif arg is not None:
                serialize_me.append(dict(((unicode(arg._meta), arg.pk),)))

        self._arguments = json.dumps(serialize_me)

    @property
    def details(self):
        if self._details:
            return json.loads(self._details)

    @details.setter
    def details(self, data):
        self._details = json.dumps(data)

    @property
    def log(self):
        return mkt.LOG_BY_ID[self.action]

    def to_string(self, type_=None):
        log_type = mkt.LOG_BY_ID[self.action]
        if type_ and hasattr(log_type, '%s_format' % type_):
            format = getattr(log_type, '%s_format' % type_)
        else:
            format = log_type.format

        # We need to copy arguments so we can remove elements from it
        # while we loop over self.arguments.
        arguments = copy(self.arguments)
        addon = None
        review = None
        version = None
        collection = None
        tag = None
        group = None
        website = None

        for arg in self.arguments:
            if isinstance(arg, Webapp) and not addon:
                addon = self.f(u'<a href="{0}">{1}</a>',
                               arg.get_url_path(), arg.name)
                arguments.remove(arg)
            if isinstance(arg, Review) and not review:
                review = self.f(u'<a href="{0}">{1}</a>',
                                arg.get_url_path(), _('Review'))
                arguments.remove(arg)
            if isinstance(arg, Version) and not version:
                text = _('Version {0}')
                version = self.f(text, arg.version)
                arguments.remove(arg)
            if isinstance(arg, Tag) and not tag:
                if arg.can_reverse():
                    tag = self.f(u'<a href="{0}">{1}</a>',
                                 arg.get_url_path(), arg.tag_text)
                else:
                    tag = self.f('{0}', arg.tag_text)
            if isinstance(arg, Group) and not group:
                group = arg.name
                arguments.remove(arg)
            if isinstance(arg, Website) and not website:
                website = self.f(u'<a href="{0}">{1}</a>',
                                 arg.get_url_path(), arg.name)
                arguments.remove(arg)

        try:
            kw = dict(addon=addon, review=review, version=version, group=group,
                      collection=collection, tag=tag,
                      user=self.user.display_name)
            return self.f(format, *arguments, **kw)
        except (AttributeError, KeyError, IndexError):
            log.warning('%d contains garbage data' % (self.id or 0))
            return 'Something magical happened.'

    def __unicode__(self):
        return self.to_string()

    def __html__(self):
        return self


# TODO: remove once we migrate to CommAtttachment (ngoke).
class ActivityLogAttachment(ModelBase):
    """
    Model for an attachment to an ActivityLog instance. Used by the Marketplace
    reviewer tools, where reviewers can attach files to comments made during
    the review process.
    """
    activity_log = models.ForeignKey('ActivityLog')
    filepath = models.CharField(max_length=255)
    description = models.CharField(max_length=255, blank=True)
    mimetype = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = 'log_activity_attachment'
        ordering = ('id',)

    def get_absolute_url(self):
        return reverse('reviewers.apps.review.attachment', args=[self.pk])

    def filename(self):
        """
        Returns the attachment's file name.
        """
        return os.path.basename(self.filepath)

    def full_path(self):
        """
        Returns the full filesystem path of the attachment.
        """
        return os.path.join(settings.REVIEWER_ATTACHMENTS_PATH, self.filepath)

    def display_name(self):
        """
        Returns a string describing the attachment suitable for front-end
        display.
        """
        display = self.description if self.description else self.filename()
        return mark_safe(bleach.clean(display))

    def is_image(self):
        """
        Returns a boolean indicating whether the attached file is an image of a
        format recognizable by the stdlib imghdr module.
        """
        return imghdr.what(self.full_path()) is not None
