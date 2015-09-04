from django import http
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

import commonware.log
from rest_framework.decorators import (authentication_classes,
                                       permission_classes)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from session_csrf import anonymous_csrf_exempt
from tower import ugettext as _

import mkt
from lib.cef_loggers import receipt_cef
from lib.crypto.receipt import SigningError
from lib.metrics import record_action
from mkt.access import acl
from mkt.api.authentication import (RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.base import cors_api_view
from mkt.constants import apps
from mkt.constants.payments import CONTRIB_NO_CHARGE
from mkt.developers.models import AppLog
from mkt.installs.utils import record as utils_record
from mkt.installs.utils import install_type
from mkt.prices.models import WebappPurchase
from mkt.receipts import forms
from mkt.receipts.utils import (create_receipt, create_test_receipt, get_uuid,
                                reissue_receipt)
from mkt.reviewers.views import reviewer_required
from mkt.site.decorators import json_view, use_master
from mkt.users.models import UserProfile
from mkt.webapps.decorators import app_view_factory
from mkt.webapps.models import Installed, Webapp
from services.verify import get_headers, Verify


log = commonware.log.getLogger('z.receipts')
app_view = app_view_factory(qs=Webapp.objects.valid)
app_all_view = app_view_factory(qs=Webapp.objects.all)


def _record(request, webapp):
    logged = request.user.is_authenticated()
    premium = webapp.is_premium()

    # Require login for premium.
    if not logged and premium:
        return http.HttpResponseRedirect(reverse('users.login'))

    ctx = {'webapp': webapp.pk}

    # Don't generate receipts if we're allowing logged-out install.
    if logged:
        is_dev = request.check_ownership(webapp, require_owner=False,
                                         ignore_disabled=True, admin=False)
        is_reviewer = acl.check_reviewer(request)
        if (not webapp.is_public() and not (is_reviewer or is_dev)):
            raise http.Http404

        if (premium and
                not webapp.has_purchased(request.user) and
                not is_reviewer and not is_dev):
            raise PermissionDenied

        # If you are reviewer, you get a user receipt. Use the reviewer tools
        # to get a reviewer receipt. App developers still get their special
        # receipt.
        install = (apps.INSTALL_TYPE_DEVELOPER if is_dev
                   else apps.INSTALL_TYPE_USER)
        # Log the install.
        installed, c = Installed.objects.get_or_create(
            webapp=webapp, user=request.user, install_type=install)

        # Get a suitable uuid for this receipt.
        uuid = get_uuid(webapp, request.user)

        error = ''
        receipt_cef.log(request, webapp, 'sign', 'Receipt requested')
        try:
            receipt = create_receipt(webapp, request.user, uuid)
        except SigningError:
            error = _('There was a problem installing the app.')

        ctx.update(receipt=receipt, error=error)
    else:
        if not webapp.is_public():
            raise http.Http404

    mkt.log(mkt.LOG.INSTALL_WEBAPP, webapp)
    record_action('install', request, {
        'app-domain': webapp.domain_from_url(webapp.origin, allow_none=True),
        'app-id': webapp.pk,
        'anonymous': request.user.is_anonymous(),
    })

    return ctx


@anonymous_csrf_exempt
@json_view
@app_all_view
@require_POST
@use_master
def record_anon(request, webapp):
    return _record(request, webapp)


@json_view
@app_all_view
@require_POST
@use_master
def record(request, webapp):
    return _record(request, webapp)


# Set the CORS headers on the response by calling get_headers.
def response(data):
    response = http.HttpResponse(data)
    for header, value in get_headers(len(data)):
        response[header] = value
    return response


@csrf_exempt
@require_POST
def verify(request, uuid):
    # Because this will be called at any point in the future,
    # use guid in the URL.
    webapp = get_object_or_404(Webapp, guid=uuid)
    receipt = request.read()
    verify = Verify(receipt, request.META)
    output = verify.check_without_purchase()

    # Only reviewers or the developers can use this which is different
    # from the standard receipt verification. The user is contained in the
    # receipt.
    if verify.user_id:
        try:
            user = UserProfile.objects.get(pk=verify.user_id)
        except UserProfile.DoesNotExist:
            user = None

        if user and (acl.action_allowed_user(user, 'Apps', 'Review') or
                     webapp.has_author(user)):
            mkt.log(mkt.LOG.RECEIPT_CHECKED, webapp, user=user)
            return response(output)

    return response(verify.invalid())


@app_all_view
@json_view
@require_POST
def issue(request, webapp):
    user = request.user
    review = acl.action_allowed_user(user, 'Apps', 'Review') if user else None
    developer = webapp.has_author(user)
    if not (review or developer):
        raise PermissionDenied

    install, flavour = ((apps.INSTALL_TYPE_REVIEWER, 'reviewer') if review
                        else (apps.INSTALL_TYPE_DEVELOPER, 'developer'))
    installed, c = Installed.objects.safer_get_or_create(
        webapp=webapp, user=request.user, install_type=install)

    error = ''
    receipt_cef.log(request, webapp, 'sign',
                    'Receipt signing for %s' % flavour)
    receipt = None
    try:
        receipt = create_receipt(webapp, user, get_uuid(webapp, user),
                                 flavour=flavour)
    except SigningError:
        error = _('There was a problem installing the app.')

    return {'webapp': webapp.pk, 'receipt': receipt, 'error': error}


@json_view
@reviewer_required
def check(request, uuid):
    # Because this will be called at any point in the future,
    # use guid in the URL.
    webapp = get_object_or_404(Webapp, guid=uuid)
    qs = (AppLog.objects.order_by('-created')
                .filter(webapp=webapp,
                        activity_log__action=mkt.LOG.RECEIPT_CHECKED.id))
    return {'status': qs.exists()}


# These methods are for the test of receipts in the devhub.
def devhub_install(request):
    return render(request, 'receipts/test_manifest.html',
                  {'form': forms.TestInstall()})


@anonymous_csrf_exempt
@json_view
@require_POST
def devhub_receipt(request):
    form = forms.TestInstall(request.POST)
    if form.is_valid():
        data = form.cleaned_data

        if data['receipt_type'] == 'none':
            return {'receipt': '', 'error': ''}

        receipt_cef.log(request, None, 'sign', 'Test receipt signing')
        receipt = create_test_receipt(data['root'], data['receipt_type'])
        return {'receipt': receipt, 'error': ''}

    return {'receipt': '', 'error': form.errors}


def devhub_details(request):
    return render(request, 'receipts/test_details.html')


@cors_api_view(['POST'],
               headers=('content-type', 'accept', 'x-fxpay-version'))
@authentication_classes([])
@permission_classes((AllowAny,))
def devhub_verify(request, status):
    receipt = request.read()
    verify = Verify(receipt, request.META)
    return Response(verify.check_without_db(status))


@cors_api_view(['POST'],
               headers=('content-type', 'accept', 'x-fxpay-version'))
@authentication_classes([RestOAuthAuthentication,
                         RestSharedSecretAuthentication])
@permission_classes([IsAuthenticated])
def install(request):
    form = forms.ReceiptForm(request.DATA)

    if not form.is_valid():
        return Response({'error_message': form.errors}, status=400)

    obj = form.cleaned_data['app']
    type_ = install_type(request, obj)

    if type_ == apps.INSTALL_TYPE_DEVELOPER:
        receipt = install_record(obj, request,
                                 apps.INSTALL_TYPE_DEVELOPER)
    else:
        # The app must be public and if its a premium app, you
        # must have purchased it.
        if not obj.is_public():
            log.info('App not public: %s' % obj.pk)
            return Response('App not public.', status=403)

        if (obj.is_premium() and
                not obj.has_purchased(request.user)):
            # Apps that are premium but have no charge will get an
            # automatic purchase record created. This will ensure that
            # the receipt will work into the future if the price changes.
            if obj.premium and not obj.premium.price.price:
                log.info('Create purchase record: {0}'.format(obj.pk))
                WebappPurchase.objects.get_or_create(
                    webapp=obj, user=request.user, type=CONTRIB_NO_CHARGE)
            else:
                log.info('App not purchased: app ID={a}; user={u}'
                         .format(a=obj.pk, u=request.user))
                return Response('You have not purchased this app.', status=402)
        receipt = install_record(obj, request, type_)
    utils_record(request, obj)
    return Response({'receipt': receipt}, status=201)


def install_record(obj, request, install_type):
    # Generate or re-use an existing install record.
    installed, created = Installed.objects.get_or_create(
        webapp=obj, user=request.user,
        install_type=install_type)

    log.info('Installed record %s: %s' % (
        'created' if created else 're-used',
        obj.pk))

    log.info('Creating receipt: %s' % obj.pk)
    receipt_cef.log(request._request, obj, 'sign', 'Receipt signing')
    uuid = get_uuid(installed.webapp, installed.user)
    return create_receipt(installed.webapp, installed.user, uuid)


@cors_api_view(['POST'],
               headers=('content-type', 'accept', 'x-fxpay-version'))
@permission_classes((AllowAny,))
def test_receipt(request):
    form = forms.TestInstall(request.DATA)
    if not form.is_valid():
        return Response({'error_message': form.errors}, status=400)

    receipt_cef.log(request._request, None, 'sign', 'Test receipt signing')
    data = {
        'receipt': create_test_receipt(form.cleaned_data['root'],
                                       form.cleaned_data['receipt_type'])
    }
    return Response(data, status=201)


@cors_api_view(['POST'],
               headers=('content-type', 'accept', 'x-fxpay-version'))
@permission_classes((AllowAny,))
def reissue(request):
    """
    Reissues an existing receipt, provided from the client. Will only do
    so if the receipt is a full receipt and expired.
    """
    raw = request.read()
    verify = Verify(raw, request.META)
    output = verify.check_full()

    # We will only re-sign expired receipts.
    if output['status'] != 'expired':
        log.info('Receipt not expired returned: {0}'.format(output))
        receipt_cef.log(request._request, None, 'sign',
                        'Receipt reissue failed')
        output['receipt'] = ''
        return Response(output, status=400)

    receipt_cef.log(request._request, None, 'sign', 'Receipt reissue signing')
    return Response({'reason': '', 'receipt': reissue_receipt(raw),
                     'status': 'expired'})
