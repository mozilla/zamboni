import json

from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.shortcuts import redirect
from django.utils.translation.trans_real import to_language

import commonware.log
from rest_framework import mixins
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.status import (HTTP_201_CREATED, HTTP_202_ACCEPTED,
                                   HTTP_400_BAD_REQUEST)
from rest_framework.viewsets import GenericViewSet

import mkt
from lib.metrics import record_action
from mkt.api.authentication import (RestAnonymousAuthentication,
                                    RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.base import CORSMixin, MarketplaceView
from mkt.api.forms import NewPackagedForm, PreviewJSONForm
from mkt.api.permissions import (AllowAppOwner, AllowRelatedAppOwner, AnyOf,
                                 GroupPermission)
from mkt.constants.applications import DEVICE_GAIA
from mkt.developers import tasks
from mkt.developers.decorators import dev_required
from mkt.developers.forms import (AppFormMedia, CategoryForm, NewManifestForm,
                                  PreviewForm, PreviewFormSet)
from mkt.developers.utils import escalate_prerelease_permissions
from mkt.files.models import FileUpload
from mkt.site.decorators import login_required, use_master
from mkt.site.utils import render
from mkt.submit.forms import AppDetailsBasicForm
from mkt.submit.models import AppSubmissionChecklist
from mkt.submit.serializers import (AppStatusSerializer, FileUploadSerializer,
                                    PreviewSerializer)
from mkt.users.models import UserProfile
from mkt.webapps.models import AddonUser, Preview, Webapp

from . import forms
from .decorators import read_dev_agreement_required, submit_step


log = commonware.log.getLogger('z.submit')


def submit(request):
    """Determine which step to redirect user to."""
    if not request.user.is_authenticated():
        return proceed(request)
    # If dev has already agreed, continue to next step.
    user = UserProfile.objects.get(pk=request.user.id)
    if not user.read_dev_agreement:
        return redirect('submit.app.terms')
    return manifest(request)


def proceed(request):
    """
    This is a fake "Terms" view that we overlay the login.
    We link here from the Developer Hub landing page.
    """
    if request.user.is_authenticated():
        return submit(request)
    agreement_form = forms.DevAgreementForm({'read_dev_agreement': True},
                                            instance=None, request=request)
    return render(request, 'submit/terms.html',
                  {'step': 'terms', 'agreement_form': agreement_form,
                   'proceed': True})


@login_required
@submit_step('terms')
def terms(request):
    # If dev has already agreed, continue to next step.
    if request.user.is_authenticated() and request.user.read_dev_agreement:
        return manifest(request)

    agreement_form = forms.DevAgreementForm(
        request.POST or {'read_dev_agreement': True},
        instance=request.user,
        request=request)
    if request.POST and agreement_form.is_valid():
        agreement_form.save()
        return redirect('submit.app')
    return render(request, 'submit/terms.html',
                  {'step': 'terms', 'agreement_form': agreement_form})


@login_required
@read_dev_agreement_required
@submit_step('manifest')
def manifest(request):

    form = forms.NewWebappForm(request.POST or None, request=request)

    features_form = forms.AppFeaturesForm(request.POST or None)
    features_form_valid = features_form.is_valid()

    if (request.method == 'POST' and form.is_valid() and
            features_form_valid):

        upload = form.cleaned_data['upload']
        addon = Webapp.from_upload(upload, is_packaged=form.is_packaged())
        file_obj = addon.latest_version.all_files[0]

        if form.is_packaged():
            validation = json.loads(upload.validation)
            escalate_prerelease_permissions(
                addon, validation, addon.latest_version)

        addon.addondevicetype_set.get_or_create(
            device_type=DEVICE_GAIA.id)

        if addon.has_icon_in_manifest(file_obj):
            # Fetch the icon, do polling.
            addon.update(icon_type='image/png')
        else:
            # In this case there is no need to do any polling.
            addon.update(icon_type='')

        AddonUser(addon=addon, user=request.user).save()
        # Checking it once. Checking it twice.
        AppSubmissionChecklist.objects.create(addon=addon, terms=True,
                                              manifest=True, details=False)

        # Create feature profile.
        addon.latest_version.features.update(**features_form.cleaned_data)

        tasks.fetch_icon.delay(addon.pk, file_obj.pk)

        return redirect('submit.app.details', addon.app_slug)

    return render(request, 'submit/manifest.html',
                  {'step': 'manifest', 'features_form': features_form,
                   'form': form})


@dev_required
@submit_step('details')
def details(request, addon_id, addon):
    # Name, Slug, Description, Privacy Policy, Homepage URL, Support URL,
    # Support Email.
    form_basic = AppDetailsBasicForm(request.POST or None, instance=addon,
                                     request=request)
    form_cats = CategoryForm(request.POST or None, product=addon,
                             request=request)
    form_icon = AppFormMedia(request.POST or None, request.FILES or None,
                             instance=addon, request=request)
    form_previews = PreviewFormSet(request.POST or None, prefix='files',
                                   queryset=addon.get_previews())

    # For empty webapp-locale (or no-locale) fields that have
    # form-locale values, duplicate them to satisfy the requirement.
    form_locale = request.COOKIES.get('current_locale', '')
    app_locale = to_language(addon.default_locale)
    for name, value in request.POST.items():
        if value:
            if name.endswith(form_locale):
                basename = name[:-len(form_locale)]
            else:
                basename = name + '_'
            othername = basename + app_locale
            if not request.POST.get(othername, None):
                request.POST[othername] = value
    forms = {
        'form_basic': form_basic,
        'form_cats': form_cats,
        'form_icon': form_icon,
        'form_previews': form_previews,
    }
    if request.POST and all(f.is_valid() for f in forms.itervalues()):
        addon = form_basic.save(addon)
        form_cats.save()
        form_icon.save(addon)
        for preview in form_previews.forms:
            preview.save(addon)
        # If this is an incomplete app from the legacy submission flow, it may
        # not have device types set yet - so assume it works everywhere.
        if not addon.device_types:
            for device in mkt.DEVICE_TYPES:
                addon.addondevicetype_set.create(device_type=device)

        AppSubmissionChecklist.objects.get(addon=addon).update(details=True)

        if addon.needs_payment():
            # Paid apps get STATUS_NULL until payment information and content
            # ratings entered.
            addon.update(status=mkt.STATUS_NULL,
                         highest_status=mkt.STATUS_PENDING)

        record_action('app-submitted', request, {'app-id': addon.pk})

        return redirect('submit.app.done', addon.app_slug)

    ctx = {
        'step': 'details',
        'addon': addon,
    }
    ctx.update(forms)
    return render(request, 'submit/details.html', ctx)


@dev_required
def done(request, addon_id, addon):
    # No submit step forced on this page, we don't really care.
    return render(request, 'submit/next_steps.html',
                  {'step': 'next_steps', 'addon': addon})


@dev_required
def resume(request, addon_id, addon):
    try:
        # If it didn't go through the app submission
        # checklist. Don't die. This will be useful for
        # creating apps with an API later.
        step = addon.appsubmissionchecklist.get_next()
    except ObjectDoesNotExist:
        step = None

    return _resume(addon, step)


def _resume(addon, step):
    if step:
        if step in ['terms', 'manifest']:
            return redirect('submit.app.%s' % step)
        return redirect(reverse('submit.app.%s' % step,
                                args=[addon.app_slug]))

    return redirect(addon.get_dev_url('edit'))


class ValidationViewSet(CORSMixin, mixins.CreateModelMixin,
                        mixins.RetrieveModelMixin, GenericViewSet):
    cors_allowed_methods = ['get', 'post']
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]
    permission_classes = [AllowAny]
    model = FileUpload
    queryset = FileUpload.objects.all()
    serializer_class = FileUploadSerializer

    @use_master
    def create(self, request, *args, **kwargs):
        """
        Custom create method allowing us to re-use form logic and distinguish
        packaged app from hosted apps, applying delays to the validation task
        if necessary.

        Doesn't rely on any serializer, just forms.
        """
        data = self.request.data
        packaged = 'upload' in data
        form = (NewPackagedForm(data) if packaged
                else NewManifestForm(data))

        if not form.is_valid():
            return Response(form.errors, status=HTTP_400_BAD_REQUEST)

        if not packaged:
            upload = FileUpload.objects.create(
                user=request.user if request.user.is_authenticated() else None)
            # The hosted app validator is pretty fast.
            tasks.fetch_manifest(form.cleaned_data['manifest'], upload.pk)
        else:
            upload = form.file_upload
            # The packaged app validator is much heavier.
            tasks.validator.delay(upload.pk)

        log.info('Validation created: %s' % upload.pk)
        self.kwargs = {'pk': upload.pk}
        # Re-fetch the object, fetch_manifest() might have altered it.
        upload = self.get_object()
        serializer = self.get_serializer(upload)
        status = HTTP_201_CREATED if upload.processed else HTTP_202_ACCEPTED
        return Response(serializer.data, status=status)


class StatusViewSet(mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                    GenericViewSet):
    queryset = Webapp.objects.all()
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication]
    permission_classes = [AnyOf(AllowAppOwner,
                                GroupPermission('Admin', '%s'))]
    serializer_class = AppStatusSerializer

    def update(self, request, *args, **kwargs):
        # PUT is disallowed, only PATCH is accepted for this endpoint.
        if request.method == 'PUT':
            raise MethodNotAllowed('PUT')
        return super(StatusViewSet, self).update(request, *args, **kwargs)


class PreviewViewSet(CORSMixin, MarketplaceView, mixins.RetrieveModelMixin,
                     mixins.DestroyModelMixin, GenericViewSet):
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication]
    permission_classes = [AllowRelatedAppOwner]
    queryset = Preview.objects.all()
    cors_allowed_methods = ['get', 'post', 'delete']
    serializer_class = PreviewSerializer

    def _create(self, request, *args, **kwargs):
        """
        Handle creation. This is directly called by the @action on AppViewSet,
        allowing the URL to depend on the app id. AppViewSet passes this method
        a Webapp instance in kwargs['app'] (optionally raising a 404 if the
        app in the URL doesn't exist, or a 403 if the app belongs to someone
        else).

        Note: this method is called '_create' and not 'create' because DRF
        would automatically make an 'app-preview-list' url name if this
        method was called 'create', which we don't want - the app-preview-list
        url name needs to be generated by AppViewSet's @action to include the
        app pk.
        """
        app = kwargs['app']

        data_form = PreviewJSONForm(request.data)
        if not data_form.is_valid():
            return Response(data_form.errors, status=HTTP_400_BAD_REQUEST)

        form = PreviewForm(data_form.cleaned_data)
        if not form.is_valid():
            return Response(data_form.errors, status=HTTP_400_BAD_REQUEST)

        form.save(app)
        log.info('Preview created: %s' % form.instance)
        serializer = self.get_serializer(form.instance)
        return Response(serializer.data, status=HTTP_201_CREATED)
