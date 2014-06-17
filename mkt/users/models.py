from contextlib import contextmanager
from datetime import datetime

from django import forms
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser
from django.core import validators
from django.db import models
from django.utils import translation
from django.utils.encoding import smart_unicode
from django.utils.functional import lazy

import commonware.log
import tower
from cache_nuggets.lib import memoize
from tower import ugettext as _

import amo
import amo.models
from amo.urlresolvers import reverse
from mkt.translations.fields import NoLinksField, save_signal
from mkt.translations.query import order_by_translation


log = commonware.log.getLogger('z.users')


class UserForeignKey(models.ForeignKey):
    """
    A replacement for  models.ForeignKey('users.UserProfile').

    This field uses UserEmailField to make form fields key off the user's email
    instead of the primary key id.  We also hook up autocomplete automatically.
    """

    def __init__(self, *args, **kw):
        super(UserForeignKey, self).__init__(UserProfile, *args, **kw)

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


AbstractBaseUser._meta.get_field('password').max_length = 255


class UserProfile(amo.models.OnChangeMixin, amo.models.ModelBase,
                  AbstractBaseUser):

    USERNAME_FIELD = 'username'
    username = models.CharField(max_length=255, default='', unique=True)
    display_name = models.CharField(max_length=255, default='', null=True,
                                    blank=True)

    email = models.EmailField(unique=True, null=True)

    averagerating = models.CharField(max_length=255, blank=True, null=True)
    bio = NoLinksField(short=False)
    confirmationcode = models.CharField(max_length=255, default='',
                                        blank=True)
    deleted = models.BooleanField(default=False)
    display_collections = models.BooleanField(default=False)
    display_collections_fav = models.BooleanField(default=False)
    emailhidden = models.BooleanField(default=True)
    homepage = models.URLField(max_length=255, blank=True, default='')
    location = models.CharField(max_length=255, blank=True, default='')
    notes = models.TextField(blank=True, null=True)
    notifycompat = models.BooleanField(default=True)
    notifyevents = models.BooleanField(default=True)
    occupation = models.CharField(max_length=255, default='', blank=True)
    # This is essentially a "has_picture" flag right now
    picture_type = models.CharField(max_length=75, default='', blank=True)
    resetcode = models.CharField(max_length=255, default='', blank=True)
    resetcode_expires = models.DateTimeField(default=datetime.now, null=True,
                                             blank=True)
    read_dev_agreement = models.DateTimeField(null=True, blank=True)

    last_login_ip = models.CharField(default='', max_length=45, editable=False)
    last_login_attempt = models.DateTimeField(null=True, editable=False)
    last_login_attempt_ip = models.CharField(default='', max_length=45,
                                             editable=False)
    failed_login_attempts = models.PositiveIntegerField(default=0,
                                                        editable=False)
    source = models.PositiveIntegerField(default=amo.LOGIN_SOURCE_UNKNOWN,
                                         editable=False, db_index=True)

    is_verified = models.BooleanField(default=True)
    region = models.CharField(max_length=11, null=True, blank=True,
                              editable=False)
    lang = models.CharField(max_length=5, null=True, blank=True,
                            editable=False)

    class Meta:
        db_table = 'users'

    def __init__(self, *args, **kw):
        super(UserProfile, self).__init__(*args, **kw)
        if self.username:
            self.username = smart_unicode(self.username)

    def __unicode__(self):
        return u'%s: %s' % (self.id, self.display_name or self.username)

    def save(self, force_insert=False, force_update=False, using=None, **kwargs):
        # we have to fix stupid things that we defined poorly in remora
        if not self.resetcode_expires:
            self.resetcode_expires = datetime.now()
        super(UserProfile, self).save(force_insert, force_update, using,
                                      **kwargs)

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
        qs = self.addons.filter(type=amo.ADDON_WEBAPP)
        qs = order_by_translation(qs, 'name')
        return qs[:n]

    @amo.cached_property
    def is_developer(self):
        return self.addonuser_set.exists()

    @property
    def name(self):
        return smart_unicode(self.display_name or self.username)

    @amo.cached_property
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
        self.username = "Anonymous-%s" % self.id  # Can't be null
        self.display_name = None
        self.homepage = ""
        self.deleted = True
        self.picture_type = ""
        self.save()

    def check_password(self, raw_password):
        # BrowserID does not store a password.
        return True

    def log_login_attempt(self, successful):
        """Log a user's login attempt"""
        self.last_login_attempt = datetime.now()
        self.last_login_attempt_ip = commonware.log.get_remote_addr()

        if successful:
            log.debug(u"User (%s) logged in successfully" % self)
            self.failed_login_attempts = 0
            self.last_login_ip = commonware.log.get_remote_addr()
        else:
            log.debug(u"User (%s) failed to log in" % self)
            if self.failed_login_attempts < 16777216:
                self.failed_login_attempts += 1

        self.save()

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
                                 .filter(type=amo.CONTRIB_PURCHASE)
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
        tower.activate(lang)
        yield
        tower.activate(old)


models.signals.pre_save.connect(save_signal, sender=UserProfile,
                                dispatch_uid='userprofile_translations')


class UserNotification(amo.models.ModelBase):
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
