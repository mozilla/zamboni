import sys
import urlparse
import uuid
from decimal import Decimal

from django import http
from django.core.exceptions import ObjectDoesNotExist
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

import commonware.log

import mkt
from lib.cef_loggers import app_pay_cef
from lib.crypto.webpay import InvalidSender, parse_from_webpay
from lib.metrics import record_action
from lib.pay_server import client as solitude
from mkt.api.exceptions import AlreadyPurchased
from mkt.purchase.decorators import can_be_purchased
from mkt.purchase.models import Contribution
from mkt.site.decorators import json_view, login_required, write
from mkt.site.utils import log_cef
from mkt.users.models import UserProfile
from mkt.webapps.decorators import app_view_factory
from mkt.webapps.models import Webapp
from mkt.webpay.webpay_jwt import get_product_jwt, WebAppProduct

from . import tasks

log = commonware.log.getLogger('z.purchase')
app_view = app_view_factory(qs=Webapp.objects.valid)


@login_required
@app_view
@write
@require_POST
@json_view
@can_be_purchased
def prepare_pay(request, addon):
    if addon.is_premium() and addon.has_purchased(request.user):
        log.info('Already purchased: %d' % addon.pk)
        raise AlreadyPurchased
    return _prepare_pay(request, addon)


def _prepare_pay(request, addon):
    app_pay_cef.log(request, 'Preparing JWT', 'preparing_jwt',
                    'Preparing JWT for: %s' % (addon.pk), severity=3)

    log.debug('Starting purchase of app: {0} by user: {1}'.format(
        addon.pk, request.user))

    contribution = Contribution.objects.create(
        addon_id=addon.pk,
        amount=addon.get_price(region=request.REGION.id),
        paykey=None,
        price_tier=addon.premium.price,
        source=request.GET.get('src', ''),
        source_locale=request.LANG,
        type=mkt.CONTRIB_PENDING,
        user=request.user,
        uuid=str(uuid.uuid4()),
    )

    log.debug('Storing contrib for uuid: {0}'.format(contribution.uuid))

    return get_product_jwt(WebAppProduct(addon), contribution)


@login_required
@app_view
@write
@json_view
def pay_status(request, addon, contrib_uuid):
    """
    Return JSON dict of {status: complete|incomplete}.

    The status of the payment is only complete when it exists by uuid,
    was purchased by the logged in user, and has been marked paid by the
    JWT postback. After that the UI is free to call app/purchase/record
    to generate a receipt.
    """
    qs = Contribution.objects.filter(uuid=contrib_uuid,
                                     addon__addonpurchase__user=request.user,
                                     type=mkt.CONTRIB_PURCHASE)
    return {'status': 'complete' if qs.exists() else 'incomplete'}


def _get_user_profile(request, buyer_email):
    user_profile = UserProfile.objects.filter(email=buyer_email)

    if user_profile.exists():
        user_profile = user_profile.get()
    else:
        source = mkt.LOGIN_SOURCE_WEBPAY
        user_profile = UserProfile.objects.create(
            email=buyer_email,
            is_verified=True,
            source=source)

        log_cef('New Account', 5, request, username=buyer_email,
                signature='AUTHNOTICE',
                msg='A new account was created from Webpay (using FxA)')
        record_action('new-user', request)

    return user_profile


@csrf_exempt
@write
@require_POST
def postback(request):
    """Verify signature and set contribution to paid."""
    signed_jwt = request.POST.get('notice', '')
    try:
        data = parse_from_webpay(signed_jwt, request.META.get('REMOTE_ADDR'))
    except InvalidSender, exc:
        app_pay_cef.log(request, 'Unknown app', 'invalid_postback',
                        'Ignoring invalid JWT %r: %s' % (signed_jwt, exc),
                        severity=4)
        return http.HttpResponseBadRequest()

    pd = urlparse.parse_qs(data['request']['productData'])
    contrib_uuid = pd['contrib_uuid'][0]
    try:
        contrib = Contribution.objects.get(uuid=contrib_uuid)
    except Contribution.DoesNotExist:
        etype, val, tb = sys.exc_info()
        raise LookupError('JWT (iss:%s, aud:%s) for trans_id %s '
                          'links to contrib %s which doesn\'t exist'
                          % (data['iss'], data['aud'],
                             data['response']['transactionID'],
                             contrib_uuid)), None, tb

    trans_id = data['response']['transactionID']

    if contrib.is_inapp_simulation():
        return simulated_postback(contrib, trans_id)

    if contrib.transaction_id is not None:
        if contrib.transaction_id == trans_id:
            app_pay_cef.log(request, 'Repeat postback', 'repeat_postback',
                            'Postback sent again for: %s' % (contrib.addon.pk),
                            severity=4)
            return http.HttpResponse(trans_id)
        else:
            app_pay_cef.log(request, 'Repeat postback with new trans_id',
                            'repeat_postback_new_trans_id',
                            'Postback sent again for: %s, but with new '
                            'trans_id: %s' % (contrib.addon.pk, trans_id),
                            severity=7)
            raise LookupError(
                'JWT (iss:{iss}, aud:{aud}) for trans_id {jwt_trans} is '
                'for contrib {contrib_uuid} that is already paid and has '
                'a different trans_id: {contrib_trans}'
                .format(iss=data['iss'], aud=data['aud'],
                        jwt_trans=data['response']['transactionID'],
                        contrib_uuid=contrib_uuid,
                        contrib_trans=contrib.transaction_id))

    # Special-case free in-app products.
    if data.get('request', {}).get('pricePoint') == '0':
        solitude_buyer_uuid = data['response']['solitude_buyer_uuid']

        try:
            buyer = (solitude.api.generic
                                 .buyer
                                 .get_object_or_404)(uuid=solitude_buyer_uuid)
        except ObjectDoesNotExist:
            raise LookupError(
                'Unable to look up buyer: {uuid} in Solitude'
                .format(uuid=solitude_buyer_uuid))
        user_profile = _get_user_profile(request, buyer.get('email'))
        return free_postback(request, contrib, trans_id, user_profile)
    try:
        transaction_data = (solitude.api.generic
                                        .transaction
                                        .get_object_or_404)(uuid=trans_id)
    except ObjectDoesNotExist:
        raise LookupError(
            'Unable to look up transaction: {trans_id} in Solitude'
            .format(trans_id=trans_id))

    buyer_uri = transaction_data['buyer']

    try:
        buyer_data = solitude.api.by_url(buyer_uri).get_object_or_404()
    except ObjectDoesNotExist:
        raise LookupError(
            'Unable to look up buyer: {buyer_uri} in Solitude'
            .format(buyer_uri=buyer_uri))

    buyer_email = buyer_data['email']

    user_profile = _get_user_profile(request, buyer_email)

    log.info(u'webpay postback: fulfilling purchase for contrib {c} with '
             u'transaction {t}'.format(c=contrib, t=trans_id))
    app_pay_cef.log(request, 'Purchase complete', 'purchase_complete',
                    'Purchase complete for: %s' % (contrib.addon.pk),
                    severity=3)

    contrib.update(transaction_id=trans_id,
                   type=mkt.CONTRIB_PURCHASE,
                   user=user_profile,
                   amount=Decimal(data['response']['price']['amount']),
                   currency=data['response']['price']['currency'])

    tasks.send_purchase_receipt.delay(contrib.pk)

    return http.HttpResponse(trans_id)


def simulated_postback(contrib, trans_id):
    simulate = contrib.inapp_product.simulate_data()
    log.info(u'Got simulated payment postback; contrib={c}; '
             u'trans={t}; simulate={s}'.format(c=contrib, t=trans_id,
                                               s=simulate))
    if simulate['result'] != 'postback':
        raise NotImplementedError(
            'Not sure how exactly to update contibutions for '
            'non-successful simulations')

    contrib.update(transaction_id=trans_id, type=mkt.CONTRIB_PURCHASE)
    return http.HttpResponse(trans_id)


def free_postback(request, contrib, trans_id, user_profile):
    log.info(u'Got free product postback: fulfilling purchase for '
             u'contrib={c}; trans={t}; user={u}'.format(
                 c=contrib, t=trans_id, u=user_profile))
    app_pay_cef.log(request, 'Purchase complete', 'purchase_complete',
                    'Purchase complete for: %s' % (contrib.addon.pk),
                    severity=3)
    contrib.update(transaction_id=trans_id,
                   type=mkt.CONTRIB_PURCHASE,
                   user=user_profile)
    tasks.send_purchase_receipt.delay(contrib.pk)
    return http.HttpResponse(trans_id)


@csrf_exempt
@write
@require_POST
def chargeback(request):
    """
    Verify signature from and create a refund contribution tied
    to the original transaction.
    """
    raise NotImplementedError
