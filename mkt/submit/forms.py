import datetime
import os

from django import forms
from django.conf import settings
from django.utils.safestring import mark_safe

import basket
import happyforms
from django.utils.translation import ugettext as _, ugettext_lazy as _lazy

import mkt
from mkt.comm.utils import create_comm_note
from mkt.constants import APP_FEATURES, comm
from mkt.developers.forms import AppSupportFormMixin, verify_app_domain
from mkt.files.models import FileUpload
from mkt.files.utils import parse_addon
from mkt.reviewers.models import RereviewQueue
from mkt.site.utils import slug_validator
from mkt.tags.models import Tag
from mkt.tags.utils import clean_tags
from mkt.translations.fields import TransField
from mkt.translations.forms import TranslationFormMixin
from mkt.translations.widgets import TransInput, TransTextarea
from mkt.users.models import UserNotification
from mkt.users.notifications import app_surveys
from mkt.webapps.models import AppFeatures, BlockedSlug, Webapp


def mark_for_rereview(addon, added_devices, removed_devices):
    msg = _(u'Device(s) changed: {0}').format(', '.join(
        [_(u'Added {0}').format(unicode(mkt.DEVICE_TYPES[d].name))
         for d in added_devices] +
        [_(u'Removed {0}').format(unicode(mkt.DEVICE_TYPES[d].name))
         for d in removed_devices]))
    RereviewQueue.flag(addon, mkt.LOG.REREVIEW_DEVICES_ADDED, msg)


def mark_for_rereview_features_change(addon, added_features, removed_features):
    # L10n: {0} is the list of requirements changes.
    msg = _(u'Requirements changed: {0}').format(', '.join(
        [_(u'Added {0}').format(f) for f in added_features] +
        [_(u'Removed {0}').format(f) for f in removed_features]))
    RereviewQueue.flag(addon, mkt.LOG.REREVIEW_FEATURES_CHANGED, msg)


class DevAgreementForm(happyforms.Form):
    read_dev_agreement = forms.BooleanField(label=_lazy(u'Agree and Continue'),
                                            widget=forms.HiddenInput)
    newsletter = forms.BooleanField(required=False, label=app_surveys.label,
                                    widget=forms.CheckboxInput)

    def __init__(self, *args, **kw):
        self.instance = kw.pop('instance')
        self.request = kw.pop('request')
        super(DevAgreementForm, self).__init__(*args, **kw)

    def save(self):
        self.instance.read_dev_agreement = datetime.datetime.now()
        self.instance.save()
        if self.cleaned_data.get('newsletter'):
            UserNotification.update_or_create(
                user=self.instance,
                notification_id=app_surveys.id, update={'enabled': True})
            basket.subscribe(self.instance.email,
                             'app-dev',
                             format='H',
                             country=self.request.REGION.slug,
                             lang=self.request.LANG,
                             source_url=os.path.join(settings.SITE_URL,
                                                     'developers/submit'))


class NewWebappVersionForm(happyforms.Form):
    upload_error = _lazy(u'There was an error with your upload. '
                         u'Please try again.')
    upload = forms.ModelChoiceField(
        widget=forms.HiddenInput,
        queryset=FileUpload.objects.filter(valid=True),
        error_messages={'invalid_choice': upload_error})

    def __init__(self, *args, **kw):
        kw.pop('request', None)
        self.addon = kw.pop('addon', None)
        self._is_packaged = kw.pop('is_packaged', False)
        self.is_homescreen = False
        super(NewWebappVersionForm, self).__init__(*args, **kw)

    def clean(self):
        data = self.cleaned_data
        if 'upload' not in self.cleaned_data:
            self._errors['upload'] = self.upload_error
            return

        if self.is_packaged():
            # Now run the packaged app check, done in clean, because
            # clean_packaged needs to be processed first.

            try:
                pkg = parse_addon(data['upload'], self.addon)
            except forms.ValidationError, e:
                self._errors['upload'] = self.error_class(e.messages)
                return

            # Collect validation errors so we can display them at once.
            errors = []

            ver = pkg.get('version')
            if (ver and self.addon and
                    self.addon.versions.filter(version=ver).exists()):
                errors.append(_(u'Version %s already exists.') % ver)

            origin = pkg.get('origin')
            if origin:
                try:
                    verify_app_domain(origin, packaged=True,
                                      exclude=self.addon)
                except forms.ValidationError, e:
                    errors.append(e.message)

                if self.addon and origin != self.addon.app_domain:
                    errors.append(_('Changes to "origin" are not allowed.'))

            self.is_homescreen = pkg.get('role') == 'homescreen'

            if errors:
                self._errors['upload'] = self.error_class(errors)
                return

        else:
            # Throw an error if this is a dupe.
            # (JS sets manifest as `upload.name`.)
            try:
                verify_app_domain(data['upload'].name)
            except forms.ValidationError, e:
                self._errors['upload'] = self.error_class(e.messages)
                return

        return data

    def is_packaged(self):
        return self._is_packaged


class NewWebappForm(NewWebappVersionForm):
    ERRORS = {
        'user': _lazy('User submitting validation does not match.')
    }
    upload = forms.ModelChoiceField(
        widget=forms.HiddenInput,
        queryset=FileUpload.objects.filter(valid=True),
        error_messages={'invalid_choice': _lazy(
            u'There was an error with your upload. Please try again.')})
    packaged = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super(NewWebappForm, self).__init__(*args, **kwargs)

    def clean(self):
        data = super(NewWebappForm, self).clean()
        if not data:
            return

        upload = data.get('upload')
        if self.request and upload:
            if not (upload.user and upload.user.pk == self.request.user.pk):
                self._errors['upload'] = self.ERRORS['user']
        return data

    def is_packaged(self):
        return self._is_packaged or self.cleaned_data.get('packaged', False)


class AppDetailsBasicForm(AppSupportFormMixin, TranslationFormMixin,
                          happyforms.ModelForm):
    """Form for "Details" submission step."""
    PRIVACY_MDN_URL = (
        'https://developer.mozilla.org/Marketplace/'
        'Publishing/Policies_and_Guidelines/Privacy_policies')

    PUBLISH_CHOICES = (
        (mkt.PUBLISH_IMMEDIATE,
         _lazy(u'Publish my app and make it visible to everyone in the '
               u'Marketplace and include it in search results.')),
        (mkt.PUBLISH_PRIVATE,
         _lazy(u'Do not publish my app. Notify me and I will adjust app '
               u'visibility after it is approved.')),
    )

    app_slug = forms.CharField(max_length=30,
                               widget=forms.TextInput(attrs={'class': 'm'}))
    description = TransField(
        label=_lazy(u'Description:'),
        help_text=_lazy(u'The app description is one of the fields used to '
                        u'return search results in the Firefox Marketplace. '
                        u'The app description also appears on the app\'s '
                        u'detail page. Be sure to include a description that '
                        u'accurately represents your app.'),
        widget=TransTextarea(attrs={'rows': 4}))
    tags = forms.CharField(
        label=_lazy(u'Search Keywords:'), required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text=_lazy(
            u'The search keywords are used to return search results in the '
            u'Firefox Marketplace. Be sure to include a keywords that '
            u'accurately reflect your app.'))
    privacy_policy = TransField(
        label=_lazy(u'Privacy Policy:'),
        widget=TransTextarea(attrs={'rows': 6}),
        help_text=_lazy(
            u'A privacy policy explains how you handle data received '
            u'through your app. For example: what data do you receive? '
            u'How do you use it? Who do you share it with? Do you '
            u'receive personal information? Do you take steps to make '
            u'it anonymous? What choices do users have to control what '
            u'data you and others receive? Enter your privacy policy '
            u'link or text above.  If you don\'t have a privacy '
            u'policy, <a href="{url}" target="_blank">learn more on how to '
            u'write one.</a>'))
    homepage = TransField.adapt(forms.URLField)(
        label=_lazy(u'Homepage:'), required=False,
        widget=TransInput(attrs={'class': 'full'}),
        help_text=_lazy(
            u'If your app has another homepage, enter its address here.'))
    support_url = TransField.adapt(forms.URLField)(
        label=_lazy(u'Website:'), required=False,
        widget=TransInput(attrs={'class': 'full'}),
        help_text=_lazy(
            u'If your app has a support website or forum, enter its address '
            u'here.'))
    support_email = TransField.adapt(forms.EmailField)(
        label=_lazy(u'Email:'), required=False,
        widget=TransInput(attrs={'class': 'full'}),
        help_text=_lazy(
            u'This email address will be listed publicly on the Marketplace '
            u'and used by end users to contact you with support issues. This '
            u'email address will be listed publicly on your app details page.'
            ))
    notes = forms.CharField(
        label=_lazy(u'Your comments for reviewers:'), required=False,
        widget=forms.Textarea(attrs={'rows': 2}),
        help_text=_lazy(
            u'Your app will be reviewed by Mozilla before it becomes publicly '
            u'listed on the Marketplace. Enter any special instructions for '
            u'the app reviewers here.'))
    publish_type = forms.TypedChoiceField(
        label=_lazy(u'Once your app is approved, choose a publishing option:'),
        choices=PUBLISH_CHOICES, initial=mkt.PUBLISH_IMMEDIATE,
        widget=forms.RadioSelect())
    is_offline = forms.BooleanField(
        label=_lazy(u'My app works without an Internet connection.'),
        required=False)

    class Meta:
        model = Webapp
        fields = ('app_slug', 'description', 'privacy_policy', 'homepage',
                  'support_url', 'support_email', 'publish_type', 'is_offline')

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request')

        # TODO: remove this and put it in the field definition above.
        # See https://bugzilla.mozilla.org/show_bug.cgi?id=1072513
        privacy_field = self.base_fields['privacy_policy']
        privacy_field.help_text = mark_safe(privacy_field.help_text.format(
            url=self.PRIVACY_MDN_URL))

        if 'instance' in kwargs:
            instance = kwargs['instance']
            instance.is_offline = instance.guess_is_offline()

        super(AppDetailsBasicForm, self).__init__(*args, **kwargs)

    def clean_app_slug(self):
        slug = self.cleaned_data['app_slug']
        slug_validator(slug, lower=False)

        if slug != self.instance.app_slug:
            if Webapp.objects.filter(app_slug=slug).exists():
                raise forms.ValidationError(
                    _('This slug is already in use. Please choose another.'))

            if BlockedSlug.blocked(slug):
                raise forms.ValidationError(
                    _('The slug cannot be "%s". Please choose another.'
                      % slug))

        return slug.lower()

    def clean_tags(self):
        return clean_tags(self.request, self.cleaned_data['tags'])

    def save(self, *args, **kw):
        if self.data['notes']:
            create_comm_note(self.instance, self.instance.versions.latest(),
                             self.request.user, self.data['notes'],
                             note_type=comm.SUBMISSION)
        self.instance = super(AppDetailsBasicForm, self).save(commit=True)

        for tag_text in self.cleaned_data['tags']:
            Tag(tag_text=tag_text).save_tag(self.instance)

        return self.instance


class AppFeaturesForm(happyforms.ModelForm):
    class Meta:
        exclude = ['version']
        model = AppFeatures

    def __init__(self, *args, **kwargs):
        super(AppFeaturesForm, self).__init__(*args, **kwargs)
        if self.instance:
            self.initial_feature_keys = sorted(self.instance.to_keys())
        else:
            self.initial_feature_keys = None

    def all_fields(self):
        """
        Degeneratorizes self.__iter__(), the list of fields on the form. This
        allows further manipulation of fields: to display a subset of fields or
        order them in a specific way.
        """
        return [f for f in self.__iter__()]

    def required_api_fields(self):
        """
        All fields on the form, alphabetically sorted by help text.
        """
        return sorted(self.all_fields(), key=lambda x: x.help_text)

    def get_tooltip(self, field):
        field_id = field.name.split('_', 1)[1].upper()
        return (unicode(APP_FEATURES[field_id].get('description') or '') if
                field_id in APP_FEATURES else None)

    def get_changed_features(self):
        old_features = dict.fromkeys(self.initial_feature_keys, True)
        old_features = set(AppFeatures(**old_features).to_names())
        new_features = set(self.instance.to_names())

        added_features = new_features - old_features
        removed_features = old_features - new_features
        return added_features, removed_features

    def save(self, *args, **kwargs):
        mark_for_rereview = kwargs.pop('mark_for_rereview', True)
        addon = self.instance.version.addon
        rval = super(AppFeaturesForm, self).save(*args, **kwargs)
        # Also save the addon to update modified date and trigger a reindex.
        addon.save(update_fields=['modified'])
        # Trigger a re-review if necessary.
        if (self.instance and mark_for_rereview and
                addon.status in mkt.WEBAPPS_APPROVED_STATUSES and
                self.changed_data):
            added_features, removed_features = self.get_changed_features()
            mark_for_rereview_features_change(addon,
                                              added_features,
                                              removed_features)
        return rval
