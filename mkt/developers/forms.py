# -*- coding: utf-8 -*-
import json
import mimetypes
import os
from datetime import datetime
from zipfile import ZipFile

from django import forms
from django.conf import settings
from django.core.validators import URLValidator
from django.forms import widgets
from django.forms.extras.widgets import SelectDateWidget
from django.forms.models import modelformset_factory
from django.template.defaultfilters import filesizeformat
from django.utils import six
from django.utils.functional import lazy
from django.utils.safestring import mark_safe
from django.utils.translation import trans_real as translation

import commonware
import happyforms
import waffle
from jinja2 import escape as jinja2_escape
from jinja2.filters import do_dictsort
from mpconstants import regions as mpconstants_regions
from quieter_formset.formset import BaseModelFormSet
from tower import ugettext as _, ugettext_lazy as _lazy, ungettext as ngettext

import lib.iarc
import mkt
from lib.video import tasks as vtasks
from mkt import get_user
from mkt.access import acl
from mkt.api.models import Access
from mkt.constants import (CATEGORY_CHOICES, MAX_PACKAGED_APP_SIZE,
                           ratingsbodies)
from mkt.developers.utils import prioritize_app
from mkt.files.models import FileUpload
from mkt.files.utils import WebAppParser
from mkt.regions import REGIONS_CHOICES_SORTED_BY_NAME
from mkt.regions.utils import parse_region
from mkt.reviewers.models import RereviewQueue
from mkt.site.fields import SeparatedValuesField
from mkt.site.forms import AddonChoiceField
from mkt.site.utils import remove_icons, slug_validator, slugify
from mkt.tags.models import Tag
from mkt.tags.utils import can_edit_restricted_tags, clean_tags
from mkt.translations.fields import TransField
from mkt.translations.forms import TranslationFormMixin
from mkt.translations.models import Translation
from mkt.translations.widgets import TranslationTextarea, TransTextarea
from mkt.versions.models import Version
from mkt.webapps.models import (AddonUser, BlockedSlug, IARCInfo, Preview,
                                Webapp)
from mkt.webapps.tasks import (index_webapps, set_storefront_data,
                               update_manifests)

from . import tasks


log = commonware.log.getLogger('mkt.developers')


def region_error(region):
    return forms.ValidationError(_('You cannot select {region}.').format(
        region=unicode(parse_region(region).name)
    ))


def toggle_app_for_special_regions(request, app, enabled_regions=None):
    """Toggle for special regions (e.g., China)."""
    if not waffle.flag_is_active(request, 'special-regions'):
        return

    for region in mkt.regions.SPECIAL_REGIONS:
        status = app.geodata.get_status(region)

        if enabled_regions is not None:
            if region.id in enabled_regions:
                # If it's not already enabled, mark as pending.
                if status != mkt.STATUS_PUBLIC:
                    # Developer requested for it to be in China.
                    status = mkt.STATUS_PENDING
                    value, changed = app.geodata.set_status(region, status)
                    if changed:
                        log.info(u'[Webapp:%s] App marked as pending '
                                 u'special region (%s).' % (app, region.slug))
                        value, changed = app.geodata.set_nominated_date(
                            region, save=True)
                        log.info(u'[Webapp:%s] Setting nomination date to '
                                 u'now for region (%s).' % (app, region.slug))
            else:
                # Developer cancelled request for approval.
                status = mkt.STATUS_NULL
                value, changed = app.geodata.set_status(
                    region, status, save=True)
                if changed:
                    log.info(u'[Webapp:%s] App marked as null special '
                             u'region (%s).' % (app, region.slug))

        if status == mkt.STATUS_PUBLIC:
            # Reviewer approved for it to be in China.
            aer = app.addonexcludedregion.filter(region=region.id)
            if aer.exists():
                aer.delete()
                log.info(u'[Webapp:%s] App included in new special '
                         u'region (%s).' % (app, region.slug))
        else:
            # Developer requested for it to be in China.
            aer, created = app.addonexcludedregion.get_or_create(
                region=region.id)
            if created:
                log.info(u'[Webapp:%s] App excluded from new special '
                         u'region (%s).' % (app, region.slug))


class AuthorForm(happyforms.ModelForm):

    def clean_user(self):
        user = self.cleaned_data['user']
        if not user.read_dev_agreement:
            raise forms.ValidationError(
                _('All team members must have read and agreed to the '
                  'developer agreement.'))

        return user

    class Meta:
        model = AddonUser
        exclude = ('addon',)


class BaseModelFormSet(BaseModelFormSet):
    """
    Override the parent's is_valid to prevent deleting all forms.
    """

    def is_valid(self):
        # clean() won't get called in is_valid() if all the rows are getting
        # deleted. We can't allow deleting everything.
        rv = super(BaseModelFormSet, self).is_valid()
        return rv and not any(self.errors) and not bool(self.non_form_errors())


class BaseAuthorFormSet(BaseModelFormSet):

    def clean(self):
        if any(self.errors):
            return
        # cleaned_data could be None if it's the empty extra form.
        data = filter(None, [f.cleaned_data for f in self.forms
                             if not f.cleaned_data.get('DELETE', False)])
        if not any(d['role'] == mkt.AUTHOR_ROLE_OWNER for d in data):
            raise forms.ValidationError(_('Must have at least one owner.'))
        if not any(d['listed'] for d in data):
            raise forms.ValidationError(
                _('At least one team member must be listed.'))
        users = [d['user'] for d in data]
        if sorted(users) != sorted(set(users)):
            raise forms.ValidationError(
                _('A team member can only be listed once.'))


AuthorFormSet = modelformset_factory(AddonUser, formset=BaseAuthorFormSet,
                                     form=AuthorForm, can_delete=True, extra=0)


class DeleteForm(happyforms.Form):
    reason = forms.CharField(required=False)

    def __init__(self, request):
        super(DeleteForm, self).__init__(request.POST)


def trap_duplicate(request, manifest_url):
    # See if this user has any other apps with the same manifest.
    owned = (request.user.addonuser_set
             .filter(addon__manifest_url=manifest_url))
    if not owned:
        return
    try:
        app = owned[0].addon
    except Webapp.DoesNotExist:
        return
    error_url = app.get_dev_url()
    msg = None
    if app.status == mkt.STATUS_PUBLIC:
        msg = _(u'Oops, looks like you already submitted that manifest '
                'for %s, which is currently public. '
                '<a href="%s">Edit app</a>')
    elif app.status == mkt.STATUS_PENDING:
        msg = _(u'Oops, looks like you already submitted that manifest '
                'for %s, which is currently pending. '
                '<a href="%s">Edit app</a>')
    elif app.status == mkt.STATUS_NULL:
        msg = _(u'Oops, looks like you already submitted that manifest '
                'for %s, which is currently incomplete. '
                '<a href="%s">Resume app</a>')
    elif app.status == mkt.STATUS_REJECTED:
        msg = _(u'Oops, looks like you already submitted that manifest '
                'for %s, which is currently rejected. '
                '<a href="%s">Edit app</a>')
    elif app.status == mkt.STATUS_DISABLED:
        msg = _(u'Oops, looks like you already submitted that manifest '
                'for %s, which is currently banned on Marketplace. '
                '<a href="%s">Edit app</a>')
    elif app.disabled_by_user:
        msg = _(u'Oops, looks like you already submitted that manifest '
                'for %s, which is currently disabled. '
                '<a href="%s">Edit app</a>')
    if msg:
        return msg % (jinja2_escape(app.name), error_url)


def verify_app_domain(manifest_url, exclude=None, packaged=False):
    if packaged or waffle.switch_is_active('webapps-unique-by-domain'):
        domain = Webapp.domain_from_url(manifest_url)
        qs = Webapp.objects.filter(app_domain=domain)
        if exclude:
            qs = qs.exclude(pk=exclude.pk)
        if qs.exists():
            raise forms.ValidationError(
                _('An app already exists on this domain; '
                  'only one app per domain is allowed.'))


class PreviewForm(happyforms.ModelForm):
    file_upload = forms.FileField(required=False)
    upload_hash = forms.CharField(required=False)
    # This lets us POST the data URIs of the unsaved previews so we can still
    # show them if there were form errors.
    unsaved_image_data = forms.CharField(required=False,
                                         widget=forms.HiddenInput)
    unsaved_image_type = forms.CharField(required=False,
                                         widget=forms.HiddenInput)

    def save(self, addon, commit=True):
        if self.cleaned_data:
            self.instance.addon = addon
            if self.cleaned_data.get('DELETE'):
                # Existing preview.
                if self.instance.id:
                    self.instance.delete()
                # User has no desire to save this preview.
                return

            super(PreviewForm, self).save(commit=commit)
            if self.cleaned_data['upload_hash']:
                upload_hash = self.cleaned_data['upload_hash']
                upload_path = os.path.join(settings.TMP_PATH, 'preview',
                                           upload_hash)
                filetype = (os.path.splitext(upload_hash)[1][1:]
                                   .replace('-', '/'))
                if filetype in mkt.VIDEO_TYPES:
                    self.instance.update(filetype=filetype)
                    vtasks.resize_video.delay(upload_path, self.instance.pk,
                                              user_pk=mkt.get_user().pk,
                                              set_modified_on=[self.instance])
                else:
                    self.instance.update(filetype='image/png')
                    tasks.resize_preview.delay(upload_path, self.instance.pk,
                                               set_modified_on=[self.instance])

    class Meta:
        model = Preview
        fields = ('file_upload', 'upload_hash', 'id', 'position')


class JSONField(forms.Field):
    def to_python(self, value):
        if value == '':
            return None

        try:
            if isinstance(value, basestring):
                return json.loads(value)
        except ValueError:
            pass
        return value


class JSONMultipleChoiceField(forms.MultipleChoiceField, JSONField):
    widget = forms.CheckboxSelectMultiple


class AdminSettingsForm(PreviewForm):
    DELETE = forms.BooleanField(required=False)
    mozilla_contact = SeparatedValuesField(forms.EmailField, separator=',',
                                           required=False)
    vip_app = forms.BooleanField(required=False)
    priority_review = forms.BooleanField(required=False)
    banner_regions = JSONMultipleChoiceField(
        required=False, choices=mkt.regions.REGIONS_CHOICES_NAME)
    banner_message = TransField(required=False)

    class Meta:
        model = Preview
        fields = ('file_upload', 'upload_hash', 'position')

    def __init__(self, *args, **kw):
        # Note that this form is not inheriting from AddonFormBase, so we have
        # to get rid of 'version' ourselves instead of letting the parent class
        # do it.
        kw.pop('version', None)

        # Get the object for the app's promo `Preview` and pass it to the form.
        if kw.get('instance'):
            addon = kw.pop('instance')
            self.instance = addon
            self.promo = addon.get_promo()

        self.request = kw.pop('request', None)

        # Note: After calling `super`, `self.instance` becomes the `Preview`
        # object.
        super(AdminSettingsForm, self).__init__(*args, **kw)

        self.initial['vip_app'] = addon.vip_app
        self.initial['priority_review'] = addon.priority_review

        if self.instance:
            self.initial['mozilla_contact'] = addon.mozilla_contact

        self.initial['banner_regions'] = addon.geodata.banner_regions or []
        self.initial['banner_message'] = addon.geodata.banner_message_id

    @property
    def regions_by_id(self):
        return mkt.regions.REGIONS_CHOICES_ID_DICT

    def clean_position(self):
        return -1

    def clean_banner_regions(self):
        try:
            regions = map(int, self.cleaned_data.get('banner_regions'))
        except (TypeError, ValueError):
            # input data is not a list or data contains non-integers.
            raise forms.ValidationError(_('Invalid region(s) selected.'))

        return list(regions)

    def clean_mozilla_contact(self):
        contact = self.cleaned_data.get('mozilla_contact')
        if self.cleaned_data.get('mozilla_contact') is None:
            return u''
        return contact

    def save(self, addon, commit=True):
        if (self.cleaned_data.get('DELETE') and
                'upload_hash' not in self.changed_data and self.promo.id):
            self.promo.delete()
        elif self.promo and 'upload_hash' in self.changed_data:
            self.promo.delete()
        elif self.cleaned_data.get('upload_hash'):
            super(AdminSettingsForm, self).save(addon, True)

        updates = {
            'vip_app': self.cleaned_data.get('vip_app'),
        }
        contact = self.cleaned_data.get('mozilla_contact')
        if contact is not None:
            updates['mozilla_contact'] = contact
        if (self.cleaned_data.get('priority_review') and
                not addon.priority_review):
            # addon.priority_review gets updated within prioritize_app().
            prioritize_app(addon, self.request.user)
        else:
            updates['priority_review'] = self.cleaned_data.get(
                'priority_review')
        addon.update(**updates)

        geodata = addon.geodata
        geodata.banner_regions = self.cleaned_data.get('banner_regions')
        geodata.banner_message = self.cleaned_data.get('banner_message')
        geodata.save()

        uses_flash = self.cleaned_data.get('flash')
        af = addon.get_latest_file()
        if af is not None:
            af.update(uses_flash=bool(uses_flash))

        index_webapps.delay([addon.id])

        return addon


class BasePreviewFormSet(BaseModelFormSet):

    def clean(self):
        if any(self.errors):
            return
        at_least_one = False
        for form in self.forms:
            if (not form.cleaned_data.get('DELETE') and
                    form.cleaned_data.get('upload_hash') is not None):
                at_least_one = True
        if not at_least_one:
            raise forms.ValidationError(
                _('You must upload at least one screenshot or video.'))


PreviewFormSet = modelformset_factory(Preview, formset=BasePreviewFormSet,
                                      form=PreviewForm, can_delete=True,
                                      extra=1)


class NewManifestForm(happyforms.Form):
    manifest = forms.URLField()

    def __init__(self, *args, **kwargs):
        self.is_standalone = kwargs.pop('is_standalone', False)
        super(NewManifestForm, self).__init__(*args, **kwargs)

    def clean_manifest(self):
        manifest = self.cleaned_data['manifest']
        # Skip checking the domain for the standalone validator.
        if not self.is_standalone:
            verify_app_domain(manifest)
        return manifest


class NewPackagedAppForm(happyforms.Form):
    upload = forms.FileField()

    def __init__(self, *args, **kwargs):
        self.max_size = kwargs.pop('max_size', MAX_PACKAGED_APP_SIZE)
        self.user = kwargs.pop('user', get_user())
        self.addon = kwargs.pop('addon', None)
        self.file_upload = None
        super(NewPackagedAppForm, self).__init__(*args, **kwargs)

    def clean_upload(self):
        upload = self.cleaned_data['upload']
        errors = []

        if upload.size > self.max_size:
            errors.append({
                'type': 'error',
                'message': _('Packaged app too large for submission. Packages '
                             'must be smaller than %s.' % filesizeformat(
                                 self.max_size)),
                'tier': 1,
            })
            # Immediately raise an error, do not process the rest of the view,
            # which would read the file.
            raise self.persist_errors(errors, upload)

        manifest = None
        try:
            # Be careful to keep this as in-memory zip reading.
            manifest = ZipFile(upload, 'r').read('manifest.webapp')
        except Exception as e:
            errors.append({
                'type': 'error',
                'message': _('Error extracting manifest from zip file.'),
                'tier': 1,
            })

        origin = None
        if manifest:
            try:
                origin = WebAppParser.decode_manifest(manifest).get('origin')
            except forms.ValidationError as e:
                errors.append({
                    'type': 'error',
                    'message': ''.join(e.messages),
                    'tier': 1,
                })

        if origin:
            try:
                verify_app_domain(origin, packaged=True, exclude=self.addon)
            except forms.ValidationError, e:
                errors.append({
                    'type': 'error',
                    'message': ''.join(e.messages),
                    'tier': 1,
                })

        if errors:
            raise self.persist_errors(errors, upload)

        # Everything passed validation.
        self.file_upload = FileUpload.from_post(
            upload, upload.name, upload.size, user=self.user)

    def persist_errors(self, errors, upload):
        """
        Persist the error with this into FileUpload (but do not persist
        the file contents, which are too large) and return a ValidationError.
        """
        validation = {
            'errors': len(errors),
            'success': False,
            'messages': errors,
        }

        self.file_upload = FileUpload.objects.create(
            user=self.user, name=getattr(upload, 'name', ''),
            validation=json.dumps(validation))

        # Return a ValidationError to be raised by the view.
        return forms.ValidationError(' '.join(e['message'] for e in errors))


class AddonFormBase(TranslationFormMixin, happyforms.ModelForm):

    def __init__(self, *args, **kw):
        self.request = kw.pop('request')
        self.version = kw.pop('version', None)
        super(AddonFormBase, self).__init__(*args, **kw)

    class Meta:
        models = Webapp
        fields = ('name', 'slug')


class AppFormBasic(AddonFormBase):
    """Form to edit basic app info."""
    slug = forms.CharField(max_length=30, widget=forms.TextInput)
    manifest_url = forms.URLField()
    hosted_url = forms.CharField(
        label=_lazy(u'Hosted URL:'), required=False,
        help_text=_lazy(
            u'A URL to where your app is hosted on the web, if it exists. This'
            u' allows users to try out your app before installing it.'))
    description = TransField(
        required=True,
        label=_lazy(u'Provide a detailed description of your app'),
        help_text=_lazy(u'This description will appear on the details page.'),
        widget=TransTextarea)
    tags = forms.CharField(
        label=_lazy(u'Search Keywords:'), required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text=_lazy(
            u'The search keywords are used to return search results in the '
            u'Firefox Marketplace. Be sure to include a keywords that '
            u'accurately reflect your app.'))

    class Meta:
        model = Webapp
        fields = ('slug', 'manifest_url', 'hosted_url', 'description', 'tags')

    def __init__(self, *args, **kw):
        # Force the form to use app_slug. We want to keep
        # this under "slug" so all the js continues to work.
        kw.setdefault('initial', {})['slug'] = kw['instance'].app_slug

        super(AppFormBasic, self).__init__(*args, **kw)

        self.old_manifest_url = self.instance.manifest_url

        if self.instance.is_packaged:
            # Manifest URL cannot be changed for packaged apps.
            del self.fields['manifest_url']

        self.initial['tags'] = ', '.join(self.get_tags(self.instance))

    def clean_tags(self):
        return clean_tags(self.request, self.cleaned_data['tags'])

    def get_tags(self, addon):
        if can_edit_restricted_tags(self.request):
            return list(addon.tags.values_list('tag_text', flat=True))
        else:
            return list(addon.tags.filter(restricted=False)
                        .values_list('tag_text', flat=True))

    def _post_clean(self):
        # Switch slug to app_slug in cleaned_data and self._meta.fields so
        # we can update the app_slug field for webapps.
        try:
            self._meta.fields = list(self._meta.fields)
            slug_idx = self._meta.fields.index('slug')
            data = self.cleaned_data
            if 'slug' in data:
                data['app_slug'] = data.pop('slug')
            self._meta.fields[slug_idx] = 'app_slug'
            super(AppFormBasic, self)._post_clean()
        finally:
            self._meta.fields[slug_idx] = 'slug'

    def clean_slug(self):
        slug = self.cleaned_data['slug']
        slug_validator(slug, lower=False)

        if slug != self.instance.app_slug:
            if Webapp.objects.filter(app_slug=slug).exists():
                raise forms.ValidationError(
                    _('This slug is already in use. Please choose another.'))

            if BlockedSlug.blocked(slug):
                raise forms.ValidationError(_('The slug cannot be "%s". '
                                              'Please choose another.' % slug))

        return slug.lower()

    def clean_manifest_url(self):
        manifest_url = self.cleaned_data['manifest_url']
        # Only verify if manifest changed.
        if 'manifest_url' in self.changed_data:
            verify_app_domain(manifest_url, exclude=self.instance)
        return manifest_url

    def save(self, addon, commit=False):
        # We ignore `commit`, since we need it to be `False` so we can save
        # the ManyToMany fields on our own.
        addonform = super(AppFormBasic, self).save(commit=False)
        addonform.save()

        if 'manifest_url' in self.changed_data:
            before_url = self.old_manifest_url
            after_url = self.cleaned_data['manifest_url']

            # If a non-admin edited the manifest URL, add to Re-review Queue.
            if not acl.action_allowed(self.request, 'Admin', '%'):
                log.info(u'[Webapp:%s] (Re-review) Manifest URL changed '
                         u'from %s to %s'
                         % (self.instance, before_url, after_url))

                msg = (_(u'Manifest URL changed from {before_url} to '
                         u'{after_url}')
                       .format(before_url=before_url, after_url=after_url))

                RereviewQueue.flag(self.instance,
                                   mkt.LOG.REREVIEW_MANIFEST_URL_CHANGE, msg)

            # Refetch the new manifest.
            log.info('Manifest %s refreshed for %s'
                     % (addon.manifest_url, addon))
            update_manifests.delay([self.instance.id])

        tags_new = self.cleaned_data['tags']
        tags_old = [slugify(t, spaces=True) for t in self.get_tags(addon)]

        add_tags = set(tags_new) - set(tags_old)
        del_tags = set(tags_old) - set(tags_new)

        # Add new tags.
        for t in add_tags:
            Tag(tag_text=t).save_tag(addon)

        # Remove old tags.
        for t in del_tags:
            Tag(tag_text=t).remove_tag(addon)

        return addonform


class AppFormDetails(AddonFormBase):
    LOCALES = [(translation.to_locale(k).replace('_', '-'), v)
               for k, v in do_dictsort(settings.LANGUAGES)]

    default_locale = forms.TypedChoiceField(required=False, choices=LOCALES)
    homepage = TransField.adapt(forms.URLField)(required=False)
    privacy_policy = TransField(
        widget=TransTextarea(), required=True,
        label=_lazy(u"Please specify your app's Privacy Policy"))

    class Meta:
        model = Webapp
        fields = ('default_locale', 'homepage', 'privacy_policy')

    def clean(self):
        # Make sure we have the required translations in the new locale.
        required = ['name', 'description']
        data = self.cleaned_data
        if not self.errors and 'default_locale' in self.changed_data:
            fields = dict((k, getattr(self.instance, k + '_id'))
                          for k in required)
            locale = data['default_locale']
            ids = filter(None, fields.values())
            qs = (Translation.objects.filter(locale=locale, id__in=ids,
                                             localized_string__isnull=False)
                  .values_list('id', flat=True))
            missing = [k for k, v in fields.items() if v not in qs]
            if missing:
                raise forms.ValidationError(
                    _('Before changing your default locale you must have a '
                      'name and description in that locale. '
                      'You are missing %s.') % ', '.join(map(repr, missing)))
        return data


class AppFormMedia(AddonFormBase):
    icon_upload_hash = forms.CharField(required=False)
    unsaved_icon_data = forms.CharField(required=False,
                                        widget=forms.HiddenInput)

    class Meta:
        model = Webapp
        fields = ('icon_upload_hash', 'icon_type')

    def save(self, addon, commit=True):
        if self.cleaned_data['icon_upload_hash']:
            upload_hash = self.cleaned_data['icon_upload_hash']
            upload_path = os.path.join(settings.TMP_PATH, 'icon', upload_hash)

            dirname = addon.get_icon_dir()
            destination = os.path.join(dirname, '%s' % addon.id)

            remove_icons(destination)
            tasks.resize_icon.delay(upload_path, destination,
                                    mkt.CONTENT_ICON_SIZES,
                                    set_modified_on=[addon])

        return super(AppFormMedia, self).save(commit)


class AppSupportFormMixin(object):
    def get_default_translation_for(self, field_name):
        """
        Return the cleaned_data for the specified field_name, using the
        field's default_locale.
        """
        default_locale = self.fields[field_name].default_locale
        return self.cleaned_data.get(field_name, {}).get(default_locale, '')

    def clean_support_fields(self):
        """
        Make sure either support email or support url are present.
        """
        if ('support_email' in self._errors or
                'support_url' in self._errors):
            # If there are already errors for those fields, bail out, that
            # means at least one of them was filled, the user just needs to
            # correct the error.
            return

        support_email = self.get_default_translation_for('support_email')
        support_url = self.get_default_translation_for('support_url')

        if not support_email and not support_url:
            # Mark the fields as invalid, add an error message on a special
            # 'support' field that the template will use if necessary, not on
            # both fields individually.
            self._errors['support'] = self.error_class(
                [_('You must provide either a website, an email, or both.')])
            self._errors['support_email'] = self.error_class([''])
            self._errors['support_url'] = self.error_class([''])

    def clean(self):
        cleaned_data = super(AppSupportFormMixin, self).clean()
        self.clean_support_fields()
        return cleaned_data


class AppFormSupport(AppSupportFormMixin, AddonFormBase):
    support_url = TransField.adapt(forms.URLField)(required=False)
    support_email = TransField.adapt(forms.EmailField)(required=False)

    class Meta:
        model = Webapp
        fields = ('support_email', 'support_url')


class AppAppealForm(happyforms.Form):
    """
    If a developer's app is rejected he can make changes and request
    another review.
    """
    notes = forms.CharField(
        label=_lazy(u'Your comments'),
        required=False, widget=forms.Textarea(attrs={'rows': 2}))

    def __init__(self, *args, **kw):
        self.product = kw.pop('product', None)
        super(AppAppealForm, self).__init__(*args, **kw)

    def save(self):
        version = self.product.versions.latest()
        notes = self.cleaned_data['notes']
        if notes:
            mkt.log(mkt.LOG.WEBAPP_RESUBMIT, self.product, version,
                    details={'comments': notes})
        else:
            mkt.log(mkt.LOG.WEBAPP_RESUBMIT, self.product, version)
        # Mark app and file as pending again.
        self.product.update(status=mkt.WEBAPPS_UNREVIEWED_STATUS)
        version.all_files[0].update(status=mkt.WEBAPPS_UNREVIEWED_STATUS)
        return version


class PublishForm(happyforms.Form):
    # Publish choice wording is slightly different here than with the
    # submission flow because the app may have already been published.
    mark_safe_lazy = lazy(mark_safe, six.text_type)
    PUBLISH_CHOICES = (
        (mkt.PUBLISH_IMMEDIATE,
         mark_safe_lazy(_lazy(
             u'<b>Published</b>: Visible to everyone in the Marketplace and '
             u'included in search results and listing pages.'))),
        (mkt.PUBLISH_HIDDEN,
         mark_safe_lazy(_lazy(
             u'<b>Unlisted</b>: Visible to only people with the URL and '
             u'does not appear in search results and listing pages.'))),
    )

    # Used for setting initial form values.
    PUBLISH_MAPPING = {
        mkt.STATUS_PUBLIC: mkt.PUBLISH_IMMEDIATE,
        mkt.STATUS_UNLISTED: mkt.PUBLISH_HIDDEN,
        mkt.STATUS_APPROVED: mkt.PUBLISH_PRIVATE,
    }
    # Use in form processing to set status.
    STATUS_MAPPING = dict((v, k) for k, v in PUBLISH_MAPPING.items())

    publish_type = forms.TypedChoiceField(
        required=False, choices=PUBLISH_CHOICES, widget=forms.RadioSelect(),
        initial=0, coerce=int, label=_lazy('App Visibility:'))
    limited = forms.BooleanField(
        required=False, label=_lazy(
            u'<b>Limit to my team</b>: Visible to only Team Members.'))

    def __init__(self, *args, **kwargs):
        self.addon = kwargs.pop('addon')
        super(PublishForm, self).__init__(*args, **kwargs)

        limited = False
        publish = self.PUBLISH_MAPPING.get(self.addon.status,
                                           mkt.PUBLISH_IMMEDIATE)
        if self.addon.status == mkt.STATUS_APPROVED:
            # Special case if app is currently private.
            limited = True
            publish = mkt.PUBLISH_HIDDEN

        # Determine the current selection via STATUS to publish choice mapping.
        self.fields['publish_type'].initial = publish
        self.fields['limited'].initial = limited

        # Make the limited label safe so we can display the HTML.
        self.fields['limited'].label = mark_safe(self.fields['limited'].label)

    def save(self):
        publish = self.cleaned_data['publish_type']
        limited = self.cleaned_data['limited']

        if publish == mkt.PUBLISH_HIDDEN and limited:
            publish = mkt.PUBLISH_PRIVATE

        status = self.STATUS_MAPPING[publish]
        self.addon.update(status=status)

        mkt.log(mkt.LOG.CHANGE_STATUS, self.addon.get_status_display(),
                self.addon)
        # Call update_version, so various other bits of data update.
        self.addon.update_version()
        # Call to update names and locales if changed.
        self.addon.update_name_from_package_manifest()
        self.addon.update_supported_locales()

        set_storefront_data.delay(self.addon.pk)


class RegionForm(forms.Form):
    regions = forms.MultipleChoiceField(
        required=False, choices=[], widget=forms.CheckboxSelectMultiple,
        label=_lazy(u'Choose the regions your app will be listed in:'),
        error_messages={'required':
                        _lazy(u'You must select at least one region.')})
    special_regions = forms.MultipleChoiceField(
        required=False, widget=forms.CheckboxSelectMultiple,
        choices=[(x.id, x.name) for x in mkt.regions.SPECIAL_REGIONS])
    enable_new_regions = forms.BooleanField(
        required=False, label=_lazy(u'Enable new regions'))
    restricted = forms.TypedChoiceField(
        required=False, initial=0, coerce=int,
        choices=[(0, _lazy('Make my app available in most regions')),
                 (1, _lazy('Choose where my app is made available'))],
        widget=forms.RadioSelect(attrs={'class': 'choices'}))

    def __init__(self, *args, **kw):
        self.product = kw.pop('product', None)
        self.request = kw.pop('request', None)
        super(RegionForm, self).__init__(*args, **kw)

        self.fields['regions'].choices = REGIONS_CHOICES_SORTED_BY_NAME()

        # This is the list of the user's exclusions as we don't
        # want the user's choices to be altered by external
        # exclusions e.g. payments availability.
        user_exclusions = list(
            self.product.addonexcludedregion.values_list('region', flat=True)
        )

        # If we have excluded regions, uncheck those.
        # Otherwise, default to everything checked.
        self.regions_before = self.product.get_region_ids(
            restofworld=True,
            excluded=user_exclusions
        )

        self.initial = {
            'regions': sorted(self.regions_before),
            'restricted': int(self.product.geodata.restricted),
            'enable_new_regions': self.product.enable_new_regions,
        }

        # The checkboxes for special regions are
        #
        # - checked ... if an app has not been requested for approval in
        #   China or the app has been rejected in China.
        #
        # - unchecked ... if an app has been requested for approval in
        #   China or the app has been approved in China.
        unchecked_statuses = (mkt.STATUS_NULL, mkt.STATUS_REJECTED)

        for region in self.special_region_objs:
            if self.product.geodata.get_status(region) in unchecked_statuses:
                # If it's rejected in this region, uncheck its checkbox.
                if region.id in self.initial['regions']:
                    self.initial['regions'].remove(region.id)
            elif region.id not in self.initial['regions']:
                # If it's pending/public, check its checkbox.
                self.initial['regions'].append(region.id)

    @property
    def regions_by_id(self):
        return mkt.regions.REGIONS_CHOICES_ID_DICT

    @property
    def special_region_objs(self):
        return mkt.regions.SPECIAL_REGIONS

    @property
    def special_region_ids(self):
        return mkt.regions.SPECIAL_REGION_IDS

    @property
    def low_memory_regions(self):
        return any(region.low_memory for region in self.regions_by_id.values())

    @property
    def special_region_statuses(self):
        """Returns the null/pending/public status for each region."""
        statuses = {}
        for region in self.special_region_objs:
            statuses[region.id] = self.product.geodata.get_status_slug(region)
        return statuses

    @property
    def special_region_messages(self):
        """Returns the L10n messages for each region's status."""
        return self.product.geodata.get_status_messages()

    def is_toggling(self):
        if not self.request or not hasattr(self.request, 'POST'):
            return False
        value = self.request.POST.get('toggle-paid')
        return value if value in ('free', 'paid') else False

    def _product_is_paid(self):
        return (self.product.premium_type in mkt.ADDON_PREMIUMS or
                self.product.premium_type == mkt.ADDON_FREE_INAPP)

    def clean_regions(self):
        regions = self.cleaned_data['regions']
        if not self.is_toggling():
            if not regions:
                raise forms.ValidationError(
                    _('You must select at least one region.'))
        return regions

    def save(self):
        # Don't save regions if we are toggling.
        if self.is_toggling():
            return

        regions = [int(x) for x in self.cleaned_data['regions']]
        special_regions = [
            int(x) for x in self.cleaned_data['special_regions']
        ]
        restricted = int(self.cleaned_data['restricted'] or 0)

        if restricted:
            before = set(self.regions_before)
            after = set(regions)

            log.info(u'[Webapp:%s] App marked as restricted.' % self.product)

            # Add new region exclusions.
            to_add = before - after
            for region in to_add:
                aer, created = self.product.addonexcludedregion.get_or_create(
                    region=region)
                if created:
                    log.info(u'[Webapp:%s] Excluded from new region (%s).'
                             % (self.product, region))

            # Remove old region exclusions.
            to_remove = after - before
            for region in to_remove:
                self.product.addonexcludedregion.filter(
                    region=region).delete()
                log.info(u'[Webapp:%s] No longer excluded from region (%s).'
                         % (self.product, region))

            # If restricted, check how we should handle new regions.
            if self.cleaned_data['enable_new_regions']:
                self.product.update(enable_new_regions=True)
                log.info(u'[Webapp:%s] will be added to future regions.'
                         % self.product)
            else:
                self.product.update(enable_new_regions=False)
                log.info(u'[Webapp:%s] will not be added to future regions.'
                         % self.product)
        else:
            # If not restricted, set `enable_new_regions` to True and remove
            # currently excluded regions.
            self.product.update(enable_new_regions=True)
            self.product.addonexcludedregion.all().delete()
            log.info(u'[Webapp:%s] App marked as unrestricted.' % self.product)

        self.product.geodata.update(restricted=restricted)

        # Toggle region exclusions/statuses for special regions (e.g., China).
        toggle_app_for_special_regions(self.request, self.product,
                                       special_regions)


class CategoryForm(happyforms.Form):
    categories = forms.MultipleChoiceField(label=_lazy(u'Categories'),
                                           choices=CATEGORY_CHOICES,
                                           widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, **kw):
        self.request = kw.pop('request', None)
        self.product = kw.pop('product', None)
        super(CategoryForm, self).__init__(*args, **kw)

        self.cats_before = (list(self.product.categories)
                            if self.product.categories else [])

        self.initial['categories'] = self.cats_before

    def max_categories(self):
        return mkt.MAX_CATEGORIES

    def clean_categories(self):
        categories = self.cleaned_data['categories']
        set_categories = set(categories)
        total = len(set_categories)
        max_cat = mkt.MAX_CATEGORIES

        if total > max_cat:
            # L10n: {0} is the number of categories.
            raise forms.ValidationError(ngettext(
                'You can have only {0} category.',
                'You can have only {0} categories.',
                max_cat).format(max_cat))

        return categories

    def save(self):
        after = list(self.cleaned_data['categories'])
        self.product.update(categories=after)
        toggle_app_for_special_regions(self.request, self.product)


class DevAgreementForm(happyforms.Form):
    read_dev_agreement = forms.BooleanField(label=_lazy(u'Agree'),
                                            widget=forms.HiddenInput)

    def __init__(self, *args, **kw):
        self.instance = kw.pop('instance')
        super(DevAgreementForm, self).__init__(*args, **kw)

    def save(self):
        self.instance.read_dev_agreement = datetime.now()
        self.instance.save()


class DevNewsletterForm(happyforms.Form):
    """Devhub newsletter subscription form."""

    email = forms.EmailField(
        error_messages={'required':
                        _lazy(u'Please enter a valid email address.')},
        widget=forms.TextInput(attrs={'required': '',
                                      'placeholder':
                                      _lazy(u'Your email address')}))
    email_format = forms.ChoiceField(
        widget=forms.RadioSelect(),
        choices=(('H', 'HTML'), ('T', _lazy(u'Text'))),
        initial='H')
    privacy = forms.BooleanField(
        error_messages={'required':
                        _lazy(u'You must agree to the Privacy Policy.')})
    country = forms.ChoiceField(label=_lazy(u'Country'))

    def __init__(self, locale, *args, **kw):
        regions = mpconstants_regions.get_region(locale).REGIONS
        regions = sorted(regions.iteritems(), key=lambda x: x[1])

        super(DevNewsletterForm, self).__init__(*args, **kw)

        self.fields['country'].choices = regions
        self.fields['country'].initial = 'us'


class AppFormTechnical(AddonFormBase):
    flash = forms.BooleanField(required=False)
    is_offline = forms.BooleanField(required=False)

    class Meta:
        model = Webapp
        fields = ('is_offline', 'public_stats',)

    def __init__(self, *args, **kw):
        super(AppFormTechnical, self).__init__(*args, **kw)
        if self.version.all_files:
            self.initial['flash'] = self.version.all_files[0].uses_flash

    def save(self, addon, commit=False):
        uses_flash = self.cleaned_data.get('flash')
        self.instance = super(AppFormTechnical, self).save(commit=True)
        if self.version.all_files:
            self.version.all_files[0].update(uses_flash=bool(uses_flash))
        return self.instance


class TransactionFilterForm(happyforms.Form):
    app = AddonChoiceField(queryset=None, required=False, label=_lazy(u'App'))
    transaction_type = forms.ChoiceField(
        required=False, label=_lazy(u'Transaction Type'),
        choices=[(None, '')] + mkt.MKT_TRANSACTION_CONTRIB_TYPES.items())
    transaction_id = forms.CharField(
        required=False, label=_lazy(u'Transaction ID'))

    current_year = datetime.today().year
    years = [current_year - x for x in range(current_year - 2012)]
    date_from = forms.DateTimeField(
        required=False, widget=SelectDateWidget(years=years),
        label=_lazy(u'From'))
    date_to = forms.DateTimeField(
        required=False, widget=SelectDateWidget(years=years),
        label=_lazy(u'To'))

    def __init__(self, *args, **kwargs):
        self.apps = kwargs.pop('apps', [])
        super(TransactionFilterForm, self).__init__(*args, **kwargs)
        self.fields['app'].queryset = self.apps


class APIConsumerForm(happyforms.ModelForm):
    app_name = forms.CharField(required=False)
    oauth_leg = forms.ChoiceField(choices=(
        ('website', _lazy('Web site')),
        ('command', _lazy('Command line')))
    )
    redirect_uri = forms.CharField(validators=[URLValidator()], required=False)

    class Meta:
        model = Access
        fields = ('app_name', 'redirect_uri')

    def __init__(self, *args, **kwargs):
        super(APIConsumerForm, self).__init__(*args, **kwargs)
        if self.data.get('oauth_leg') == 'website':
            for field in ['app_name', 'redirect_uri']:
                self.fields[field].required = True


class AppVersionForm(happyforms.ModelForm):
    releasenotes = TransField(widget=TransTextarea(), required=False)
    approvalnotes = forms.CharField(
        widget=TranslationTextarea(attrs={'rows': 4}), required=False)
    publish_immediately = forms.BooleanField(
        required=False,
        label=_lazy(u'Make this the Active version of my app as soon as it '
                    u'has been reviewed and approved.'))

    class Meta:
        model = Version
        fields = ('releasenotes', 'approvalnotes')

    def __init__(self, *args, **kwargs):
        super(AppVersionForm, self).__init__(*args, **kwargs)
        self.fields['publish_immediately'].initial = (
            self.instance.addon.publish_type == mkt.PUBLISH_IMMEDIATE)

    def save(self, *args, **kwargs):
        rval = super(AppVersionForm, self).save(*args, **kwargs)
        if self.instance.all_files[0].status == mkt.STATUS_PENDING:
            # If version is pending, allow changes to publish_type.
            if self.cleaned_data.get('publish_immediately'):
                publish_type = mkt.PUBLISH_IMMEDIATE
            else:
                publish_type = mkt.PUBLISH_PRIVATE
            self.instance.addon.update(publish_type=publish_type)
        return rval


class PreloadTestPlanForm(happyforms.Form):
    agree = forms.BooleanField(
        widget=forms.CheckboxInput,
        label=_lazy(
            u'Please consider my app as a candidate to be pre-loaded on a '
            u'Firefox OS device. I agree to the terms and conditions outlined '
            u'above. I understand that this document is not a commitment to '
            u'pre-load my app.'
        ))
    test_plan = forms.FileField(
        label=_lazy(u'Upload Your Test Plan (.pdf, .xls under 2.5MB)'),
        widget=forms.FileInput(attrs={'class': 'button'}))

    def clean(self):
        """Validate test_plan file."""
        content_types = [
            'application/pdf',
            'application/vnd.pdf',
            'application/ms-excel',
            'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.'
            'sheet'
        ]
        max_upload_size = 2621440  # 2.5MB

        if 'test_plan' not in self.files:
            raise forms.ValidationError(_('Test plan required.'))

        file = self.files['test_plan']
        content_type = mimetypes.guess_type(file.name)[0]

        if content_type in content_types:
            if file._size > max_upload_size:
                msg = _('File too large. Keep size under %s. Current size %s.')
                msg = msg % (filesizeformat(max_upload_size),
                             filesizeformat(file._size))
                self._errors['test_plan'] = self.error_class([msg])
                raise forms.ValidationError(msg)
        else:
            msg = (_('Invalid file type {0}. Only {1} files are supported.')
                   .format(content_type, ', '.join(content_types)))
            self._errors['test_plan'] = self.error_class([msg])
            raise forms.ValidationError(msg)

        return self.cleaned_data


class IARCGetAppInfoForm(happyforms.Form):
    submission_id = forms.CharField()
    security_code = forms.CharField(max_length=10)

    def __init__(self, app, *args, **kwargs):
        self.app = app
        super(IARCGetAppInfoForm, self).__init__(*args, **kwargs)

    def clean_submission_id(self):
        submission_id = (
            # Also allow "subm-1234" since that's what IARC tool displays.
            self.cleaned_data['submission_id'].lower().replace('subm-', ''))

        if submission_id.isdigit():
            return int(submission_id)

        raise forms.ValidationError(_('Please enter a valid submission ID.'))

    def clean(self):
        cleaned_data = super(IARCGetAppInfoForm, self).clean()

        app = self.app
        iarc_id = cleaned_data.get('submission_id')

        if not app or not iarc_id:
            return cleaned_data

        if (not settings.IARC_ALLOW_CERT_REUSE and
            IARCInfo.objects.filter(submission_id=iarc_id)
                            .exclude(addon=app).exists()):
            del cleaned_data['submission_id']
            raise forms.ValidationError(
                _('This IARC certificate is already being used for another '
                  'app. Please create a new IARC Ratings Certificate.'))

        return cleaned_data

    def save(self, *args, **kwargs):
        app = self.app
        iarc_id = self.cleaned_data['submission_id']
        iarc_code = self.cleaned_data['security_code']
        if settings.DEBUG and iarc_id == 0:
            # A local developer is being lazy. Skip the hard work.
            app.set_iarc_info(iarc_id, iarc_code)
            app.set_descriptors([])
            app.set_interactives([])
            app.set_content_ratings({ratingsbodies.ESRB: ratingsbodies.ESRB_E})
            return

        # Generate XML.
        xml = lib.iarc.utils.render_xml(
            'get_app_info.xml',
            {'submission_id': iarc_id, 'security_code': iarc_code})

        # Process that shizzle.
        client = lib.iarc.client.get_iarc_client('services')
        resp = client.Get_App_Info(XMLString=xml)

        # Handle response.
        data = lib.iarc.utils.IARC_XML_Parser().parse_string(resp)

        if data.get('rows'):
            row = data['rows'][0]

            if 'submission_id' not in row:
                # [{'ActionStatus': 'No records found. Please try another
                #                   'criteria.', 'rowId: 1}].
                msg = _('Invalid submission ID or security code.')
                self._errors['submission_id'] = self.error_class([msg])
                log.info('[IARC] Bad GetAppInfo: %s' % row)
                raise forms.ValidationError(msg)

            # We found a rating, so store the id and code for future use.
            app.set_iarc_info(iarc_id, iarc_code)
            app.set_descriptors(row.get('descriptors', []))
            app.set_interactives(row.get('interactives', []))
            app.set_content_ratings(row.get('ratings', {}))

        else:
            msg = _('Invalid submission ID or security code.')
            self._errors['submission_id'] = self.error_class([msg])
            log.info('[IARC] Bad GetAppInfo. No rows: %s' % data)
            raise forms.ValidationError(msg)


class ContentRatingForm(happyforms.Form):
    since = forms.DateTimeField()


class MOTDForm(happyforms.Form):
    motd = forms.CharField(widget=widgets.Textarea())
