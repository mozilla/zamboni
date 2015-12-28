import json
import os
import sys
import traceback
import uuid
from collections import defaultdict
from datetime import datetime, timedelta

from django import forms as django_forms
from django import http
from django.contrib import messages
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

import commonware.log
import waffle
from rest_framework import status as http_status
from rest_framework.exceptions import ParseError
from rest_framework.generics import CreateAPIView, GenericAPIView, ListAPIView
from rest_framework.mixins import UpdateModelMixin
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.status import is_success
from session_csrf import anonymous_csrf, anonymous_csrf_exempt
from django.utils.translation import ugettext as _
from waffle.decorators import waffle_switch

import mkt
import lib.iarc
from lib.iarc.utils import get_iarc_app_title
from lib.iarc_v2.client import _iarc_app_data
from lib.iarc_v2.serializers import IARCV2RatingListSerializer
from mkt.access import acl
from mkt.api.base import CORSMixin, SlugOrIdMixin
from mkt.api.models import Access
from mkt.comm.utils import create_comm_note
from mkt.constants import comm
from mkt.developers.decorators import dev_required
from mkt.developers.forms import (
    APIConsumerForm, AppFormBasic, AppFormDetails, AppFormMedia,
    AppFormSupport, AppFormTechnical, AppVersionForm, CategoryForm,
    ContentRatingForm, IARCGetAppInfoForm, MOTDForm, NewPackagedAppForm,
    PreviewFormSet, TransactionFilterForm, trap_duplicate)
from mkt.developers.models import AppLog, IARCRequest
from mkt.developers.serializers import ContentRatingSerializer
from mkt.developers.tasks import (fetch_manifest, file_validator,
                                  run_validator, validator)
from mkt.developers.utils import (
    check_upload, escalate_prerelease_permissions, handle_vip)
from mkt.files.models import File, FileUpload
from mkt.files.utils import parse_addon
from mkt.purchase.models import Contribution
from mkt.reviewers.models import QUEUE_TARAKO
from mkt.site.decorators import (
    json_view, login_required, permission_required, use_master)
from mkt.site.storage_utils import public_storage
from mkt.site.utils import escape_all, paginate
from mkt.submit.forms import AppFeaturesForm, NewWebappVersionForm
from mkt.translations.query import order_by_translation
from mkt.users.models import UserProfile
from mkt.users.views import _clean_next_url
from mkt.versions.models import Version
from mkt.webapps.decorators import app_view
from mkt.webapps.models import AddonUser, ContentRating, IARCInfo, Webapp
from mkt.webapps.tasks import _update_manifest, update_manifests
from mkt.zadmin.models import set_config, unmemoized_get_config

from . import forms


log = commonware.log.getLogger('z.devhub')


# We use a session cookie to make sure people see the dev agreement.
DEV_AGREEMENT_COOKIE = 'yes-I-read-the-dev-agreement'


def addon_listing(request):
    """Set up the queryset and filtering for addon listing for Dashboard."""
    qs = request.user.addons.all()
    sorting = 'name'
    if request.GET.get('sort') == 'created':
        sorting = 'created'
        qs = qs.order_by('-created')
    else:
        qs = order_by_translation(qs, 'name')
    return qs, sorting


@anonymous_csrf
def login(request, template=None):
    if 'to' in request.GET:
        request = _clean_next_url(request)
    data = {
        'to': request.GET.get('to')
    }

    if request.user.is_authenticated():
        return http.HttpResponseRedirect(
            request.GET.get('to', settings.LOGIN_REDIRECT_URL))

    return render(request, 'developers/login.html', data)


def home(request):
    return index(request)


@login_required
def index(request):
    # This is a temporary redirect.
    return redirect('mkt.developers.apps')


@login_required
def dashboard(request):
    addons, sorting = addon_listing(request)
    addons = paginate(request, addons, per_page=10)
    data = {
        'addons': addons,
        'sorting': sorting,
        'motd': unmemoized_get_config('mkt_developers_motd')
    }
    return render(request, 'developers/apps/dashboard.html', data)


@dev_required(staff=True)
def edit(request, addon_id, addon):
    data = {
        'page': 'edit',
        'addon': addon,
        'valid_slug': addon.app_slug,
        'tags': addon.tags.not_blocked().values_list('tag_text', flat=True),
        'previews': addon.get_previews(),
        'version': addon.current_version or addon.latest_version
    }
    if not addon.is_packaged and data['version']:
        data['feature_list'] = data['version'].features.to_names()
    if acl.action_allowed(request, 'Apps', 'Configure'):
        data['admin_settings_form'] = forms.AdminSettingsForm(instance=addon,
                                                              request=request)
    return render(request, 'developers/apps/edit.html', data)


@dev_required(owner_for_post=True)
@require_POST
def delete(request, addon_id, addon):
    # Database deletes only allowed for free or incomplete addons.
    if not addon.can_be_deleted():
        msg = _('Paid apps cannot be deleted. Disable this app instead.')
        messages.error(request, msg)
        return redirect(addon.get_dev_url('versions'))

    # TODO: Force the user to re-auth with BrowserID (this DeleteForm doesn't
    # ask the user for his password)
    form = forms.DeleteForm(request)
    if form.is_valid():
        reason = form.cleaned_data.get('reason', '')
        addon.delete(msg='Removed via devhub', reason=reason)
        messages.success(request, _('App deleted.'))
        # Preserve query-string parameters if we were directed from Dashboard.
        return redirect(request.GET.get('to') or
                        reverse('mkt.developers.apps'))
    else:
        msg = _('Password was incorrect. App was not deleted.')
        messages.error(request, msg)
        return redirect(addon.get_dev_url('versions'))


@dev_required
@require_POST
def enable(request, addon_id, addon):
    addon.update(disabled_by_user=False)
    mkt.log(mkt.LOG.USER_ENABLE, addon)
    return redirect(addon.get_dev_url('versions'))


@dev_required
@require_POST
def disable(request, addon_id, addon):
    addon.update(disabled_by_user=True)
    mkt.log(mkt.LOG.USER_DISABLE, addon)
    return redirect(addon.get_dev_url('versions'))


@dev_required
def status(request, addon_id, addon):
    appeal_form = forms.AppAppealForm(request.POST, product=addon)
    upload_form = NewWebappVersionForm(request.POST or None, is_packaged=True,
                                       addon=addon, request=request)
    publish_form = forms.PublishForm(
        request.POST if 'publish-app' in request.POST else None, addon=addon)

    if request.method == 'POST':
        if 'resubmit-app' in request.POST and appeal_form.is_valid():
            if not addon.is_rated():
                # Cannot resubmit without content ratings.
                return http.HttpResponseForbidden(
                    'This app must obtain content ratings before being '
                    'resubmitted.')

            appeal_form.save()
            create_comm_note(addon, addon.latest_version,
                             request.user, appeal_form.data['notes'],
                             note_type=comm.RESUBMISSION)
            if addon.vip_app:
                handle_vip(addon, addon.latest_version, request.user)

            messages.success(request, _('App successfully resubmitted.'))
            return redirect(addon.get_dev_url('versions'))

        elif 'upload-version' in request.POST and upload_form.is_valid():
            upload = upload_form.cleaned_data['upload']
            ver = Version.from_upload(upload, addon)

            # Update addon status now that the new version was saved.
            addon.update_status()

            res = run_validator(ver.all_files[0].file_path)
            validation_result = json.loads(res)

            # Escalate the version if it uses prerelease permissions.
            escalate_prerelease_permissions(addon, validation_result, ver)

            # Set all detected features as True and save them.
            keys = ['has_%s' % feature.lower()
                    for feature in validation_result['feature_profile']]
            data = defaultdict.fromkeys(keys, True)

            # Set "Smartphone-Sized Displays" if it's a mobile-only app.
            qhd_devices = (set((mkt.DEVICE_GAIA,)),
                           set((mkt.DEVICE_MOBILE,)),
                           set((mkt.DEVICE_GAIA, mkt.DEVICE_MOBILE,)))
            mobile_only = (addon.latest_version and
                           addon.latest_version.features.has_qhd)
            if set(addon.device_types) in qhd_devices or mobile_only:
                data['has_qhd'] = True

            # Update feature profile for this version.
            ver.features.update(**data)

            messages.success(request, _('New version successfully added.'))
            log.info('[Webapp:%s] New version created id=%s from upload: %s'
                     % (addon, ver.pk, upload))

            if addon.vip_app:
                handle_vip(addon, ver, request.user)

            return redirect(addon.get_dev_url('versions.edit', args=[ver.pk]))

        elif 'publish-app' in request.POST and publish_form.is_valid():
            publish_form.save()
            return redirect(addon.get_dev_url('versions'))

    ctx = {
        'addon': addon,
        'appeal_form': appeal_form,
        'is_tarako': addon.tags.filter(tag_text=QUEUE_TARAKO).exists(),
        'publish_form': publish_form,
        'upload_form': upload_form,
    }

    # Used in the delete version modal.
    if addon.is_packaged:
        versions = addon.versions.values('id', 'version')
        version_strings = dict((v['id'], v) for v in versions)
        version_strings['num'] = len(versions)
        ctx['version_strings'] = json.dumps(version_strings)

    if addon.status == mkt.STATUS_REJECTED:
        try:
            entry = (AppLog.objects
                     .filter(addon=addon,
                             activity_log__action=mkt.LOG.REJECT_VERSION.id)
                     .order_by('-created'))[0]
        except IndexError:
            entry = None
        # This contains the rejection reason and timestamp.
        ctx['rejection'] = entry and entry.activity_log

    return render(request, 'developers/apps/status.html', ctx)


@permission_required([('DeveloperMOTD', 'Edit')])
def motd(request):
    message = unmemoized_get_config('mkt_developers_motd')
    form = MOTDForm(request.POST or None, initial={'motd': message})
    if request.method == 'POST' and form and form.is_valid():
        set_config('mkt_developers_motd', form.cleaned_data['motd'])
        messages.success(request, _('Changes successfully saved.'))
        return redirect(reverse('mkt.developers.motd'))
    return render(request, 'developers/motd.html', {'form': form})


def _submission_msgs():
    return {
        'complete': _('Congratulations, your app submission is now complete '
                      'and will be reviewed shortly!'),
        'content_ratings_saved': _('Content ratings successfully saved.'),
    }


def _ratings_success_msg(app, old_status, old_modified):
    """
    Ratings can be created via IARC pinging our API.
    Thus we can't display a success message via the standard POST/req/res.
    To workaround, we stored app's rating's `modified` from edit page.
    When hitting back to the ratings summary page, calc what msg to show.

    old_status -- app status during ratings edit page.
    old_modified -- rating modified datetime during ratings edit page.
    """
    if old_modified:
        old_modified = datetime.strptime(
            old_modified, '%Y-%m-%dT%H:%M:%S')

    if old_status != app.status:
        # App just created a rating to go pending, show 'app now pending'.
        return _submission_msgs()['complete']

    elif old_modified != app.last_rated_time():
        # App create/update rating, but was already pending/public, show 'ok'.
        return _submission_msgs()['content_ratings_saved']


@dev_required
def content_ratings(request, addon_id, addon):
    if not addon.is_rated():
        return redirect(addon.get_dev_url('ratings_edit'))

    # Use _ratings_success_msg to display success message.
    session = request.session
    app_id = str(addon.id)
    if 'ratings_edit' in session and app_id in session['ratings_edit']:
        prev_state = session['ratings_edit'][app_id]
        msg = _ratings_success_msg(
            addon, prev_state['app_status'], prev_state['rating_modified'])
        messages.success(request, msg) if msg else None
        del session['ratings_edit'][app_id]  # Clear msg so not shown again.
        request.session.modified = True

    return render(request, 'developers/apps/ratings/ratings_summary.html',
                  {'addon': addon})


@dev_required
def content_ratings_edit(request, addon_id, addon):
    initial = {}
    try:
        app_info = addon.iarc_info
        initial['submission_id'] = app_info.submission_id
        initial['security_code'] = app_info.security_code
    except IARCInfo.DoesNotExist:
        pass
    messages.debug(request,
                   "DEBUG mode on; you may use IARC id 0 with any code")
    form = IARCGetAppInfoForm(data=request.POST or None, initial=initial,
                              app=addon)

    if request.method == 'POST' and form.is_valid():
        try:
            form.save()
            return redirect(addon.get_dev_url('ratings'))
        except django_forms.ValidationError:
            pass  # Fall through to show the form error.

    # Save some information for _ratings_success_msg.
    if 'ratings_edit' not in request.session:
        request.session['ratings_edit'] = {}
    last_rated = addon.last_rated_time()
    request.session['ratings_edit'][str(addon.id)] = {
        'app_status': addon.status,
        'rating_modified': last_rated.isoformat() if last_rated else None
    }
    request.session.modified = True

    ctx = {
        'addon': addon,
        'app_name': get_iarc_app_title(addon),
        'form': form,
        'company': addon.latest_version.developer_name,
        'now': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

    if waffle.switch_is_active('iarc-upgrade-v2'):
        try:
            iarc_request = addon.iarc_request
            outdated = (datetime.now() - iarc_request.created >
                        timedelta(hours=1))
            if outdated:
                # IARC request outdated. Re-create.
                iarc_request.delete()
                iarc_request = IARCRequest.objects.create(
                    app=addon, uuid=uuid.uuid4())
        except IARCRequest.DoesNotExist:
            # No IARC request exists. Create.
            iarc_request = IARCRequest.objects.create(
                app=addon, uuid=uuid.uuid4())
        ctx['iarc_request_id'] = unicode(uuid.UUID(iarc_request.uuid))

    return render(request, 'developers/apps/ratings/ratings_edit.html', ctx)


@dev_required
def version_edit(request, addon_id, addon, version_id):
    show_features = addon.is_packaged
    formdata = request.POST if request.method == 'POST' else None
    version = get_object_or_404(Version, pk=version_id, addon=addon)
    version.addon = addon  # Avoid extra useless query.
    form = AppVersionForm(formdata, instance=version)
    all_forms = [form]

    if show_features:
        appfeatures = version.features
        appfeatures_form = AppFeaturesForm(formdata, instance=appfeatures)
        all_forms.append(appfeatures_form)

    if request.method == 'POST' and all(f.is_valid() for f in all_forms):
        [f.save() for f in all_forms]

        if f.data.get('approvalnotes'):
            create_comm_note(
                addon, version, request.user, f.data['approvalnotes'],
                note_type=comm.DEVELOPER_VERSION_NOTE_FOR_REVIEWER)

        messages.success(request, _('Version successfully edited.'))
        return redirect(addon.get_dev_url('versions'))

    context = {
        'addon': addon,
        'version': version,
        'form': form
    }

    if show_features:
        context.update({
            'appfeatures_form': appfeatures_form,
            'appfeatures': appfeatures,
            'feature_list': appfeatures.to_names(),
        })

    return render(request, 'developers/apps/version_edit.html', context)


@dev_required
@require_POST
def version_publicise(request, addon_id, addon):
    version_id = request.POST.get('version_id')
    version = get_object_or_404(Version, pk=version_id, addon=addon)

    if version.all_files[0].status == mkt.STATUS_APPROVED:
        File.objects.filter(version=version).update(status=mkt.STATUS_PUBLIC)
        mkt.log(mkt.LOG.CHANGE_VERSION_STATUS, unicode(version.status[0]),
                version)
        # Call update_version, so various other bits of data update.
        addon.update_version()

        # Call to update names and locales if changed.
        addon.update_name_from_package_manifest()
        addon.update_supported_locales()
        messages.success(request, _('Version successfully made active.'))

    return redirect(addon.get_dev_url('versions'))


@dev_required
@require_POST
def version_delete(request, addon_id, addon):
    version_id = request.POST.get('version_id')
    version = get_object_or_404(Version, pk=version_id, addon=addon)
    if version.all_files[0].status == mkt.STATUS_BLOCKED:
        raise PermissionDenied
    version.delete()
    messages.success(request,
                     _('Version "{0}" deleted.').format(version.version))
    return redirect(addon.get_dev_url('versions'))


@dev_required(owner_for_post=True)
def ownership(request, addon_id, addon):
    # Authors.
    qs = AddonUser.objects.filter(addon=addon).order_by('position')
    user_form = forms.AuthorFormSet(request.POST or None, queryset=qs)

    if request.method == 'POST' and user_form.is_valid():
        # Authors.
        authors = user_form.save(commit=False)
        redirect_url = addon.get_dev_url('owner')

        for author in authors:
            action = None
            if not author.id or author.user_id != author._original_user_id:
                action = mkt.LOG.ADD_USER_WITH_ROLE
                author.addon = addon
            elif author.role != author._original_role:
                action = mkt.LOG.CHANGE_USER_WITH_ROLE

            author.save()
            if action:
                mkt.log(action, author.user, author.get_role_display(), addon)

            if (author._original_user_id and
                    author.user_id != author._original_user_id):
                mkt.log(mkt.LOG.REMOVE_USER_WITH_ROLE,
                        (UserProfile, author._original_user_id),
                        author.get_role_display(), addon)
                # Unsubscribe user from emails (Commbadge).
                author.user.comm_thread_cc.filter(
                    thread___addon=addon).delete()

        for author in user_form.deleted_objects:
            author.delete()
            if author.user_id == request.user.id:
                # The current user removed their own access to the app.
                redirect_url = reverse('mkt.developers.apps')

            mkt.log(mkt.LOG.REMOVE_USER_WITH_ROLE, author.user,
                    author.get_role_display(), addon)
            # Unsubscribe user from emails (Commbadge).
            author.user.comm_thread_cc.filter(thread___addon=addon).delete()

        messages.success(request, _('Changes successfully saved.'))
        return redirect(redirect_url)

    ctx = dict(addon=addon, user_form=user_form)
    return render(request, 'developers/apps/owner.html', ctx)


@anonymous_csrf
def validate_app(request):
    return render(request, 'developers/validate_app.html', {
        'upload_hosted_url':
            reverse('mkt.developers.standalone_hosted_upload'),
        'upload_packaged_url':
            reverse('mkt.developers.standalone_packaged_upload'),
    })


@require_POST
def _upload(request, addon=None, is_standalone=False):
    user = request.user
    # If there is no user, default to None (saves the file upload as anon).
    form = NewPackagedAppForm(request.POST, request.FILES,
                              user=user if user.is_authenticated() else None,
                              addon=addon)
    if form.is_valid():
        validator.delay(form.file_upload.pk)

    if addon:
        return redirect('mkt.developers.upload_detail_for_addon',
                        addon.app_slug, form.file_upload.pk)
    elif is_standalone:
        return redirect('mkt.developers.standalone_upload_detail',
                        'packaged', form.file_upload.pk)
    else:
        return redirect('mkt.developers.upload_detail',
                        form.file_upload.pk, 'json')


@login_required
def upload_new(*args, **kwargs):
    return _upload(*args, **kwargs)


@anonymous_csrf
def standalone_packaged_upload(request):
    return _upload(request, is_standalone=True)


@dev_required
def upload_for_addon(request, addon_id, addon):
    return _upload(request, addon=addon)


@dev_required
@require_POST
def refresh_manifest(request, addon_id, addon):
    log.info('Manifest %s refreshed for %s' % (addon.manifest_url, addon))
    _update_manifest(addon_id, True, {})
    return http.HttpResponse(status=204)


@require_POST
@json_view
@use_master
def _upload_manifest(request, is_standalone=False):
    form = forms.NewManifestForm(request.POST, is_standalone=is_standalone)
    if (not is_standalone and
            waffle.switch_is_active('webapps-unique-by-domain')):
        # Helpful error if user already submitted the same manifest.
        dup_msg = trap_duplicate(request, request.POST.get('manifest'))
        if dup_msg:
            return {
                'validation': {
                    'errors': 1, 'success': False,
                    'messages': [{
                        'type': 'error', 'message': dup_msg, 'tier': 1}]
                }
            }
    if form.is_valid():
        user = request.user if request.user.is_authenticated() else None
        upload = FileUpload.objects.create(user=user)
        fetch_manifest.delay(form.cleaned_data['manifest'], upload.pk)
        if is_standalone:
            return redirect('mkt.developers.standalone_upload_detail',
                            'hosted', upload.pk)
        else:
            return redirect('mkt.developers.upload_detail', upload.pk, 'json')
    else:
        error_text = _('There was an error with the submission.')
        if 'manifest' in form.errors:
            error_text = ' '.join(form.errors['manifest'])
        error_message = {'type': 'error', 'message': error_text, 'tier': 1}

        v = {'errors': 1, 'success': False, 'messages': [error_message]}
        return make_validation_result(dict(validation=v, error=error_text))


@login_required
def upload_manifest(*args, **kwargs):
    """Wrapper function for `_upload_manifest` so we can keep the
    standalone validator separate from the manifest upload stuff.

    """
    return _upload_manifest(*args, **kwargs)


def standalone_hosted_upload(request):
    return _upload_manifest(request, is_standalone=True)


@json_view
@anonymous_csrf_exempt
def standalone_upload_detail(request, type_, uuid):
    upload = get_object_or_404(FileUpload, uuid=uuid)
    url = reverse('mkt.developers.standalone_upload_detail',
                  args=[type_, uuid])
    return upload_validation_context(request, upload, url=url)


@dev_required
@json_view
def upload_detail_for_addon(request, addon_id, addon, uuid):
    upload = get_object_or_404(FileUpload, uuid=uuid)
    return json_upload_detail(request, upload, addon=addon)


def make_validation_result(data):
    """Safe wrapper around JSON dict containing a validation result."""
    if not settings.EXPOSE_VALIDATOR_TRACEBACKS:
        if data['error']:
            data['error'] = _('An error occurred validating the manifest.')
    if data['validation']:
        for msg in data['validation']['messages']:
            for k, v in msg.items():
                msg[k] = escape_all(v, linkify=k in ('message', 'description'))
    return data


@dev_required(allow_editors=True)
def file_validation(request, addon_id, addon, file_id):
    file = get_object_or_404(File, id=file_id)

    v = addon.get_dev_url('json_file_validation', args=[file.id])
    return render(request, 'developers/validation.html',
                  dict(validate_url=v, filename=file.filename,
                       timestamp=file.created, addon=addon))


@json_view
@csrf_exempt
@dev_required(allow_editors=True)
def json_file_validation(request, addon_id, addon, file_id):
    file = get_object_or_404(File, id=file_id)
    if not file.has_been_validated:
        if request.method != 'POST':
            return http.HttpResponseNotAllowed(['POST'])

        try:
            v_result = file_validator(file.id)
        except Exception, exc:
            log.error('file_validator(%s): %s' % (file.id, exc))
            error = "\n".join(traceback.format_exception(*sys.exc_info()))
            return make_validation_result({'validation': '',
                                           'error': error})
    else:
        v_result = file.validation
    validation = json.loads(v_result.validation)

    return make_validation_result(dict(validation=validation, error=None))


@json_view
def json_upload_detail(request, upload, addon=None):
    result = upload_validation_context(request, upload, addon=addon)
    if result['validation']:
        if result['validation']['errors'] == 0:
            try:
                parse_addon(upload, addon=addon)
            except django_forms.ValidationError, exc:
                m = []
                for msg in exc.messages:
                    # Simulate a validation error so the UI displays it.
                    m.append({'type': 'error', 'message': msg, 'tier': 1})
                v = make_validation_result(dict(error='',
                                                validation=dict(messages=m)))
                return json_view.error(v)
    return result


def upload_validation_context(request, upload, addon=None, url=None):
    if not settings.VALIDATE_ADDONS:
        upload.task_error = ''
        upload.validation = json.dumps({'errors': 0, 'messages': [],
                                        'metadata': {}, 'notices': 0,
                                        'warnings': 0})
        upload.save()

    validation = json.loads(upload.validation) if upload.validation else ''
    if not url:
        if addon:
            url = reverse('mkt.developers.upload_detail_for_addon',
                          args=[addon.app_slug, upload.uuid])
        else:
            url = reverse('mkt.developers.upload_detail',
                          args=[upload.uuid, 'json'])
    report_url = reverse('mkt.developers.upload_detail', args=[upload.uuid])

    return make_validation_result(dict(upload=upload.uuid,
                                       validation=validation,
                                       error=upload.task_error, url=url,
                                       full_report_url=report_url))


def upload_detail(request, uuid, format='html'):
    upload = get_object_or_404(FileUpload, uuid=uuid)

    if format == 'json' or request.is_ajax():
        return json_upload_detail(request, upload)

    validate_url = reverse('mkt.developers.standalone_upload_detail',
                           args=['hosted', upload.uuid])
    return render(request, 'developers/validation.html',
                  dict(validate_url=validate_url, filename=upload.name,
                       timestamp=upload.created))


@dev_required(staff=True)
def addons_section(request, addon_id, addon, section, editable=False):
    models = {'basic': AppFormBasic,
              'media': AppFormMedia,
              'details': AppFormDetails,
              'support': AppFormSupport,
              'technical': AppFormTechnical,
              'admin': forms.AdminSettingsForm}

    is_dev = acl.check_addon_ownership(request, addon, dev=True)

    if section not in models:
        raise http.Http404()

    version = addon.current_version or addon.latest_version

    tags, previews = [], []
    cat_form = appfeatures = appfeatures_form = version_form = None
    formdata = request.POST if request.method == 'POST' else None

    # Permissions checks.
    # Only app owners can edit any of the details of their apps.
    # Users with 'Apps:Configure' can edit the admin settings.
    if ((section != 'admin' and not is_dev) or
            (section == 'admin' and
             not acl.action_allowed(request, 'Apps', 'Configure') and
             not acl.action_allowed(request, 'Apps', 'ViewConfiguration'))):
        raise PermissionDenied

    if section == 'basic':
        cat_form = CategoryForm(formdata, product=addon, request=request)
        # Only show/use the release notes form for hosted apps, packaged apps
        # can do that from the version edit page.
        if not addon.is_packaged:
            version_form = AppVersionForm(formdata, instance=version)
        tags = addon.tags.not_blocked().values_list('tag_text', flat=True)

    elif section == 'media':
        previews = PreviewFormSet(
            request.POST or None, prefix='files',
            queryset=addon.get_previews())

    elif section == 'technical':
        # Only show/use the features form for hosted apps, packaged apps
        # can do that from the version edit page.
        if not addon.is_packaged:
            appfeatures = version.features
            appfeatures_form = AppFeaturesForm(formdata, instance=appfeatures)

    # Get the slug before the form alters it to the form data.
    valid_slug = addon.app_slug
    if editable:
        if request.method == 'POST':

            if (section == 'admin' and
                    not acl.action_allowed(request, 'Apps', 'Configure')):
                raise PermissionDenied

            form = models[section](formdata, request.FILES, instance=addon,
                                   version=version, request=request)

            all_forms = [form, previews]
            for additional_form in (appfeatures_form, cat_form, version_form):
                if additional_form:
                    all_forms.append(additional_form)

            if all(not f or f.is_valid() for f in all_forms):
                if cat_form:
                    cat_form.save()

                addon = form.save(addon)

                if appfeatures_form:
                    appfeatures_form.save()

                if version_form:
                    # We are re-using version_form without displaying all its
                    # fields, so we need to override the boolean fields,
                    # otherwise they'd be considered empty and therefore False.
                    version_form.cleaned_data['publish_immediately'] = (
                        version_form.fields['publish_immediately'].initial)
                    version_form.save()

                if 'manifest_url' in form.changed_data:
                    addon.update(
                        app_domain=addon.domain_from_url(addon.manifest_url))
                    update_manifests([addon.pk])

                if previews:
                    for preview in previews.forms:
                        preview.save(addon)

                editable = False
                if section == 'media':
                    mkt.log(mkt.LOG.CHANGE_ICON, addon)
                else:
                    mkt.log(mkt.LOG.EDIT_PROPERTIES, addon)

                valid_slug = addon.app_slug
        else:
            form = models[section](instance=addon, version=version,
                                   request=request)
    else:
        form = False

    data = {
        'addon': addon,
        'version': version,
        'form': form,
        'editable': editable,
        'tags': tags,
        'cat_form': cat_form,
        'version_form': version_form,
        'preview_form': previews,
        'valid_slug': valid_slug,
    }

    if appfeatures_form and appfeatures:
        data.update({
            'appfeatures': appfeatures,
            'feature_list': appfeatures.to_names(),
            'appfeatures_form': appfeatures_form,
        })

    return render(request, 'developers/apps/edit/%s.html' % section, data)


@never_cache
@dev_required(skip_submit_check=True)
@json_view
def image_status(request, addon_id, addon, icon_size=64):
    # Default icon needs no checking.
    if not addon.icon_type or addon.icon_type.split('/')[0] == 'icon':
        icons = True
    else:
        icons = public_storage.exists(
            os.path.join(addon.get_icon_dir(), '%s-%s.png' % (
                addon.id, icon_size)))
    previews = all(public_storage.exists(p.thumbnail_path)
                   for p in addon.get_previews())
    return {'overall': icons and previews,
            'icons': icons,
            'previews': previews}


@json_view
def ajax_upload_media(request, upload_type):
    errors = []
    upload_hash = ''

    if 'upload_image' in request.FILES:
        upload_preview = request.FILES['upload_image']
        upload_preview.seek(0)
        content_type = upload_preview.content_type
        errors, upload_hash = check_upload(upload_preview, upload_type,
                                           content_type)

    else:
        errors.append(_('There was an error uploading your preview.'))

    if errors:
        upload_hash = ''

    return {'upload_hash': upload_hash, 'errors': errors}


@dev_required
def upload_media(request, addon_id, addon, upload_type):
    return ajax_upload_media(request, upload_type)


@dev_required
@require_POST
def remove_locale(request, addon_id, addon):
    locale = request.POST.get('locale')
    if locale and locale != addon.default_locale:
        addon.remove_locale(locale)
        return http.HttpResponse()
    return http.HttpResponseBadRequest()


def docs(request, doc_name=None, doc_page=None):
    filename = ''

    all_docs = {'policies': ['agreement']}

    if doc_name and doc_name in all_docs:
        filename = '%s.html' % doc_name
        if doc_page and doc_page in all_docs[doc_name]:
            filename = '%s-%s.html' % (doc_name, doc_page)
        else:
            # TODO: Temporary until we have a `policies` docs index.
            filename = None

    if not filename:
        return redirect('ecosystem.landing')

    return render(request, 'developers/docs/%s' % filename)


@login_required
def terms(request):
    form = forms.DevAgreementForm({'read_dev_agreement': True},
                                  instance=request.user)
    if request.POST and form.is_valid():
        form.save()
        log.info('Dev agreement agreed for user: %s' % request.user.pk)
        if request.GET.get('to') and request.GET['to'].startswith('/'):
            return redirect(request.GET['to'])
        messages.success(request, _('Terms of service accepted.'))
    return render(request, 'developers/terms.html',
                  {'accepted': request.user.read_dev_agreement,
                   'agreement_form': form})


def terms_standalone(request):
    return render(request, 'developers/terms_standalone.html')


@login_required
def api(request):
    roles = request.user.groups.filter(name='Admins').exists()
    form = APIConsumerForm()
    if roles:
        messages.error(request,
                       _('Users with the admin role cannot use the API.'))

    elif request.method == 'POST':
        if 'delete' in request.POST:
            try:
                consumer = Access.objects.get(pk=request.POST.get('consumer'),
                                              user=request.user)
                consumer.delete()
            except Access.DoesNotExist:
                messages.error(request, _('No such API key.'))
        else:
            access = Access.create_for_user(request.user)
            form = APIConsumerForm(request.POST, instance=access)
            if form.is_valid():
                form.save()
                messages.success(request, _('New API key generated.'))
            else:
                access.delete()
    consumers = list(Access.objects.filter(user=request.user))
    return render(request, 'developers/api.html',
                  {'consumers': consumers, 'roles': roles, 'form': form,
                   'domain': settings.DOMAIN, 'site_url': settings.SITE_URL})


@app_view
@require_POST
@permission_required([('Admin', '%'), ('Apps', 'Configure')])
def blocklist(request, addon):
    """
    Blocklists the app by creating a new version/file.
    """
    if addon.status != mkt.STATUS_BLOCKED:
        addon.create_blocklisted_version()
        messages.success(request, _('Created blocklisted version.'))
    else:
        messages.info(request, _('App already blocklisted.'))

    return redirect(addon.get_dev_url('versions'))


@waffle_switch('view-transactions')
@login_required
def transactions(request):
    form, transactions = _get_transactions(request)
    return render(
        request, 'developers/transactions.html',
        {'form': form, 'CONTRIB_TYPES': mkt.CONTRIB_TYPES,
         'count': transactions.count(),
         'transactions': paginate(request, transactions, per_page=50)})


def _get_transactions(request):
    apps = addon_listing(request)[0]
    transactions = Contribution.objects.filter(addon__in=list(apps),
                                               type__in=mkt.CONTRIB_TYPES)

    form = TransactionFilterForm(request.GET, apps=apps)
    if form.is_valid():
        transactions = _filter_transactions(transactions, form.cleaned_data)
    return form, transactions


def _filter_transactions(qs, data):
    """Handle search filters and queries for transactions."""
    filter_mapping = {'app': 'addon_id',
                      'transaction_type': 'type',
                      'transaction_id': 'uuid',
                      'date_from': 'created__gte',
                      'date_to': 'created__lte'}
    for form_field, db_field in filter_mapping.iteritems():
        if data.get(form_field):
            try:
                qs = qs.filter(**{db_field: data[form_field]})
            except ValueError:
                continue
    return qs


def testing(request):
    return render(request, 'developers/testing.html')


class ContentRatingList(CORSMixin, SlugOrIdMixin, ListAPIView):
    model = ContentRating
    serializer_class = ContentRatingSerializer
    permission_classes = (AllowAny,)
    cors_allowed_methods = ['get']

    queryset = Webapp.objects.all()
    slug_field = 'app_slug'

    def get(self, request, *args, **kwargs):
        app = self.get_object()

        self.queryset = app.content_ratings.all()

        if 'since' in request.GET:
            form = ContentRatingForm(request.GET)
            if form.is_valid():
                self.queryset = self.queryset.filter(
                    modified__gt=form.cleaned_data['since'])

        if not self.queryset.exists():
            raise http.Http404()

        return super(ContentRatingList, self).get(self, request)


class ContentRatingsPingback(CORSMixin, SlugOrIdMixin, CreateAPIView):
    cors_allowed_methods = ['post']
    parser_classes = (lib.iarc.utils.IARC_JSON_Parser,)
    permission_classes = (AllowAny,)

    queryset = Webapp.objects.all()
    slug_field = 'app_slug'

    def post(self, request, pk, *args, **kwargs):
        log.info(u'Received IARC pingback for app:%s' % pk)

        if request.content_type != 'application/json':
            log.info(u'IARC pingback not of content-type "application/json"')
            return Response({
                'detail': "Endpoint only accepts 'application/json'."
            }, status=http_status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)

        app = self.get_object()
        data = request.data[0]
        if settings.DEBUG:
            log.debug(u'%s' % data)

        if app.iarc_token() != data.get('token'):
            # Verify token.
            log.info(u'Token mismatch in IARC pingback for app:%s' % app.id)
            return Response({'detail': 'Token mismatch'},
                            status=http_status.HTTP_400_BAD_REQUEST)

        if data.get('ratings'):
            # Double-check with IARC that it's the correct rating.
            if not self.verify_data(data):
                return Response('The ratings do not match the submission ID.',
                                status=http_status.HTTP_400_BAD_REQUEST)

            log.info(u'Setting content ratings from IARC pingback for app:%s' %
                     app.id)
            # We found a rating, so store the id and code for future use.
            if 'submission_id' in data and 'security_code' in data:
                app.set_iarc_info(data['submission_id'], data['security_code'])

            # Update status if incomplete status.
            # Do this before set_content_ratings to not prematurely trigger
            # a refresh.
            log.info('Checking app:%s completeness after IARC pingback.'
                     % app.id)
            if (app.has_incomplete_status() and
                    app.is_fully_complete(ignore_ratings=True)):
                log.info('Updating app status from IARC pingback for app:%s' %
                         app.id)
                # Don't call update to prevent recursion in update_status.
                app.update(status=mkt.STATUS_PENDING)
                log.info('Updated app status from IARC pingback for app:%s' %
                         app.id)
            elif app.has_incomplete_status():
                log.info('Reasons for app:%s incompleteness after IARC '
                         'pingback: %s' % (app.id, app.completion_errors()))

            app.set_descriptors(data.get('descriptors', []))
            app.set_interactives(data.get('interactives', []))
            # Set content ratings last since it triggers a refresh on Content
            # Ratings page. We want descriptors and interactives visible by
            # the time it's refreshed.
            app.set_content_ratings(data.get('ratings', {}))

        return Response('ok')

    def verify_data(self, data):
        client = lib.iarc.client.get_iarc_client('services')
        xml = lib.iarc.utils.render_xml('get_app_info.xml', data)
        resp = client.Get_App_Info(XMLString=xml)
        check_data = lib.iarc.utils.IARC_XML_Parser().parse_string(resp)
        try:
            check_data = check_data.get('rows', [])[0]
        except IndexError:
            return False

        rates_bad = data.get('ratings') != check_data.get('ratings')
        inter_bad = (set(data.get('interactives', [])) !=
                     set(check_data.get('interactives', [])))
        descs_bad = (set(data.get('descriptors', [])) !=
                     set(check_data.get('descriptors', [])))
        if rates_bad:
            log.error('IARC pingback did not match rating %s vs %s' %
                      (data.get('ratings'), check_data.get('ratings')))
        if inter_bad:
            log.error('IARC pingback did not match interactives %s vs %s' %
                      (data.get('interactives'),
                       check_data.get('interactives')))
        if descs_bad:
            log.error('IARC pingback did not match descriptors %s vs %s' %
                      (data.get('descriptors'), check_data.get('descriptors')))
        if rates_bad or inter_bad or descs_bad:
            return False

        return True


class ContentRatingsPingbackV2(CORSMixin, UpdateModelMixin, GenericAPIView):
    """Pingback API for IARC v2.

    Should conform to the PushCert API spec. Assumes that the RatingList is
    always sent with PushCert, so we don't need to call SearchCert afterwards
    to get the ratings."""
    cors_allowed_methods = ['post']
    permission_classes = (AllowAny,)
    queryset = IARCRequest.objects.all()
    serializer_class = IARCV2RatingListSerializer
    lookup_field = 'uuid'

    def get_object(self, queryset=None):
        request = self.request
        try:
            self.kwargs[self.lookup_field] = request.data['StoreRequestID']
        except KeyError:
            raise ParseError('Need a StoreRequestID')
        self.object = super(ContentRatingsPingbackV2, self).get_object().app
        return self.object

    def finalize_response(self, request, response, *args, **kwargs):
        """Alter response to conform to IARC spec (which is not REST)."""
        if is_success(response.status_code):
            # Override data, because IARC wants a specific response and does
            # not care about our serialized data.
            response.data = _iarc_app_data(self.object)
            response.data['StatusCode'] = 'Success'
        else:
            response.data['StatusCode'] = 'InvalidRequest'
        return super(ContentRatingsPingbackV2, self).finalize_response(
            request, response, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        # IARC sends a POST, but what we really want is to update some data,
        # passing an object to the serializer. So we implement post() to match
        # the HTTP verb but really have it call update() behind the scenes.
        return self.update(request, *args, **kwargs)
