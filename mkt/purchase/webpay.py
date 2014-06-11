import sys
import urlparse
import uuid
from decimal import Decimal

from django import http
from django.views.decorators.csrf import csrf_exempt

import commonware.log

import amo
from amo.decorators import json_view, login_required, post_required, write
from lib.cef_loggers import app_pay_cef
from lib.crypto.webpay import InvalidSender, parse_from_webpay
from mkt.api.exceptions import AlreadyPurchased
from mkt.purchase.decorators import can_be_purchased
from mkt.purchase.models import Contribution
from mkt.webapps.decorators import app_view_factory
from mkt.webapps.models import Webapp
from mkt.webpay.webpay_jwt import get_product_jwt, WebAppProduct

from . import tasks

log = commonware.log.getLogger('z.purchase')
app_view = app_view_factory(qs=Webapp.objects.valid)


@login_required
@app_view
@write
@post_required
@json_view
@can_be_purchased
def prepare_pay(request, addon):
    if addon.is_premium() and addon.has_purchased(request.amo_user):
        log.info('Already purchased: %d' % addon.pk)
        raise AlreadyPurchased

    app_pay_cef.log(request, 'Preparing JWT', 'preparing_jwt',
                    'Preparing JWT for: %s' % (addon.pk), severity=3)

    log.debug('Starting purchase of app: {0} by user: {1}'.format(
        addon.pk, request.amo_user))

    contribution = Contribution.objects.create(
        addon_id=addon.pk,
        amount=addon.get_price(region=request.REGION.id),
        paykey=None,
        price_tier=addon.premium.price,
        source=request.REQUEST.get('src', ''),
        source_locale=request.LANG,
        type=amo.CONTRIB_PENDING,
        user=request.amo_user,
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
    au = request.amo_user
    qs = Contribution.objects.filter(uuid=contrib_uuid,
                                     addon__addonpurchase__user=au,
                                     type=amo.CONTRIB_PURCHASE)
    return {'status': 'complete' if qs.exists() else 'incomplete'}


@csrf_exempt
@write
@post_required
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
            raise LookupError('JWT (iss:%s, aud:%s) for trans_id %s is for '
                              'contrib %s that is already paid and has '
                              'existing differnet trans_id: %s'
                              % (data['iss'], data['aud'],
                                 data['response']['transactionID'],
                                 contrib_uuid, contrib.transaction_id))

    log.info('webpay postback: fulfilling purchase for contrib %s with '
             'transaction %s' % (contrib, trans_id))
    app_pay_cef.log(request, 'Purchase complete', 'purchase_complete',
                    'Purchase complete for: %s' % (contrib.addon.pk),
                    severity=3)
    contrib.update(transaction_id=trans_id, type=amo.CONTRIB_PURCHASE,
                   amount=Decimal(data['response']['price']['amount']),
                   currency=data['response']['price']['currency'])

    if contrib.user:
        tasks.send_purchase_receipt.delay(contrib.pk)
    else:
        log.info('No user for contribution {c}; not sending receipt'
                 .format(c=contrib))
    return http.HttpResponse(trans_id)


@csrf_exempt
@write
@post_required
def chargeback(request):
    """
    Verify signature from and create a refund contribution tied
    to the original transaction.
    """
    raise NotImplementedError
