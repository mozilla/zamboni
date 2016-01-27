import hashlib
from contextlib import contextmanager

from django import forms
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser
from django.core import validators
from django.core.urlresolvers import reverse
from django.db import models
from django.utils import translation
from django.utils.encoding import smart_unicode
from django.utils.functional import lazy

import commonware.log
from cache_nuggets.lib import memoize
from django.utils.translation import ugettext as _

import mkt
from mkt.site.models import ModelBase, OnChangeMixin
from mkt.site.utils import cached_property
from mkt.translations.fields import save_signal
from mkt.translations.query import order_by_translation


log = commonware.log.getLogger('z.users')


class UserForeignKey(models.ForeignKey):
    """
    A replacement for  models.ForeignKey('users.UserProfile').

    This field uses UserEmailField to make form fields key off the user's email
    instead of the primary key id.  We also hook up autocomplete automatically.
    """

    def __init__(self, to=None, **kwargs):
        super(UserForeignKey, self).__init__(UserProfile, **kwargs)

    def value_from_object(self, obj):
        return getattr(obj, self.name).email

    def formfield(self, **kw):
        defaults = {'form_class': UserEmailField}
        defaults.update(kw)
        return models.Field.formfield(self, **defaults)


class UserEmailField(forms.EmailField):

    def clean(self, value):
        if value in validators.EMPTY_VALUES:
            raise forms.ValidationError(self.error_messages['required'])
        try:
            return UserProfile.objects.get(email=value)
        except UserProfile.DoesNotExist:
            raise forms.ValidationError(_('No user with that email.'))

    def widget_attrs(self, widget):
        lazy_reverse = lazy(reverse, str)
        return {'class': 'email-autocomplete',
                'data-src': lazy_reverse('users.ajax')}


class UserProfile(OnChangeMixin, ModelBase, AbstractBaseUser):

    USERNAME_FIELD = 'email'
    fxa_uid = models.CharField(max_length=255, unique=True, blank=True,
                               null=True)
    display_name = models.CharField(max_length=255, default='', null=True,
                                    blank=True)
    email = models.EmailField(unique=True, null=True)
    deleted = models.BooleanField(default=False)
    last_login_ip = models.CharField(default='', max_length=45, editable=False)
    source = models.PositiveIntegerField(default=mkt.LOGIN_SOURCE_UNKNOWN,
                                         editable=False, db_index=True)

    is_verified = models.BooleanField(default=True)
    region = models.CharField(max_length=11, null=True, blank=True,
                              editable=False)
    lang = models.CharField(max_length=10, null=True, blank=True,
                            editable=False)
    enable_recommendations = models.BooleanField(default=True)

    # Here, "read" actually means "signed".
    shown_dev_agreement = models.DateTimeField(null=True, blank=True)
    read_dev_agreement = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'users'

    def __init__(self, *args, **kw):
        super(UserProfile, self).__init__(*args, **kw)

    def __unicode__(self):
        return u'%s: %s' % (self.id, self.name)

    def get_full_name(self):
        return self.display_name

    @property
    def is_superuser(self):
        return self.groups.filter(rules='*:*').exists()

    @property
    def is_staff(self):
        from mkt.access import acl
        return acl.action_allowed_user(self, 'Admin', '%')

    def has_perm(self, perm, obj=None):
        return self.is_superuser

    def has_module_perms(self, app_label):
        return self.is_superuser

    def get_backend(self):
        return 'django_browserid.auth.BrowserIDBackend'

    def set_backend(self, val):
        pass

    backend = property(get_backend, set_backend)

    def is_anonymous(self):
        return False

    def get_url_path(self, src=None):
        # See: bug 880767.
        return '#'

    def my_apps(self, n=8):
        """Returns n apps"""
        return order_by_translation(self.addons.all(), 'name')[:n]

    @property
    def recommendation_hash(self):
        return hashlib.sha256('{id}{key}'.format(
            id=self.id, key=settings.SECRET_KEY)).hexdigest()

    @cached_property
    def is_developer(self):
        return self.addonuser_set.exists()

    @property
    def name(self):
        return smart_unicode(self.display_name or 'user-%s' % self.id)

    @cached_property
    def reviews(self):
        """All reviews that are not dev replies."""
        qs = self._reviews_all.filter(reply_to=None)
        # Force the query to occur immediately. Several
        # reviews-related tests hang if this isn't done.
        return qs

    def anonymize(self):
        log.info(u"User (%s: <%s>) is being anonymized." % (self, self.email))
        self.email = None
        self.password = "sha512$Anonymous$Password"
        self.fxa_uid = None
        self.display_name = None
        self.homepage = ""
        self.deleted = True
        self.picture_type = ""
        self.save()

    def check_password(self, raw_password):
        # BrowserID does not store a password.
        return True

    def purchase_ids(self):
        """
        I'm special casing this because we use purchase_ids a lot in the site
        and we are not caching empty querysets in cache-machine.
        That means that when the site is first launched we are having a
        lot of empty queries hit.

        We can probably do this in smarter fashion by making cache-machine
        cache empty queries on an as need basis.
        """
        # Circular import
        from mkt.prices.models import AddonPurchase

        @memoize(prefix='users:purchase-ids')
        def ids(pk):
            return (AddonPurchase.objects.filter(user=pk)
                                 .values_list('addon_id', flat=True)
                                 .filter(type=mkt.CONTRIB_PURCHASE)
                                 .order_by('pk'))
        return ids(self.pk)

    @contextmanager
    def activate_lang(self):
        """
        Activate the language for the user. If none is set will go to the site
        default which is en-US.
        """
        lang = self.lang if self.lang else settings.LANGUAGE_CODE
        old = translation.get_language()
        translation.activate(lang)
        yield
        translation.activate(old)


models.signals.pre_save.connect(save_signal, sender=UserProfile,
                                dispatch_uid='userprofile_translations')


class UserNotification(ModelBase):
    user = models.ForeignKey(UserProfile, related_name='notifications')
    notification_id = models.IntegerField()
    enabled = models.BooleanField(default=False)

    class Meta:
        db_table = 'users_notifications'

    @staticmethod
    def update_or_create(update={}, **kwargs):
        rows = UserNotification.objects.filter(**kwargs).update(**update)
        if not rows:
            update.update(dict(**kwargs))
            UserNotification.objects.create(**update)
