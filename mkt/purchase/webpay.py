import calendar
import sys
import time
import urlparse
import uuid
from decimal import Decimal
from urllib import urlencode

from django import http
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt

import bleach
import commonware.log

from addons.decorators import addon_view_factory
import amo
from amo.decorators import json_view, login_required, post_required, write
from amo.helpers import absolutify
from amo.urlresolvers import reverse
from lib.cef_loggers import app_pay_cef
from lib.crypto.webpay import (InvalidSender, parse_from_webpay,
                               sign_webpay_jwt)
from mkt.api.exceptions import AlreadyPurchased
from mkt.purchase.decorators import can_be_purchased
from mkt.webapps.models import Webapp
from stats.models import ClientData, Contribution

from . import tasks

log = commonware.log.getLogger('z.purchase')
addon_view = addon_view_factory(qs=Webapp.objects.valid)


def make_ext_id(addon_pk):
    """
    Generates a webpay/solitude external ID given an addon's primary key.
    """
    # This namespace is currently necessary because app products
    # are mixed into an application's own in-app products.
    # Maybe we can fix that.
    # Also, we may use various dev/stage servers with the same
    # Bango test API.
    domain = getattr(settings, 'DOMAIN', None)
    if not domain:
        domain = 'marketplace-dev'
    ext_id = domain.split('.')[0]
    return '%s:%s' % (ext_id, addon_pk)


def make_ext_id_inapp(inapp_pk):
    """
    Generates a webpay/solitude external ID given an in app item's primary key.
    """
    return 'inapp.%s' % make_ext_id(inapp_pk)


@login_required
@addon_view
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

    user = request.amo_user
    region = request.REGION
    source = request.REQUEST.get('src', '')
    lang = request.LANG
    client_data = ClientData.get_or_create(request)

    return _prepare_pay(addon, user=user, region=region,
                        source=source, lang=lang,
                        client_data=client_data)


def _prepare_pay(addon, user=None, region=None,
                 source=None, lang=None, client_data=None):
    """Prepare a JWT for paid apps to pass into navigator.pay()"""
    log.debug('Starting purchase of app: %s by user: %s'
              % (addon.pk, user.pk))

    amount = addon.get_price(region=region.id)
    uuid_ = str(uuid.uuid4())

    log.debug('Storing contrib for uuid: %s' % uuid_)
    Contribution.objects.create(addon_id=addon.id, amount=amount,
                                source=source, source_locale=lang,
                                uuid=str(uuid_), type=amo.CONTRIB_PENDING,
                                paykey=None, user=user,
                                price_tier=addon.premium.price,
                                client_data=client_data)

    # Until atob() supports encoded HTML we are stripping all tags.
    # See bug 831524
    app_description = bleach.clean(unicode(addon.description), strip=True,
                                   tags=[])

    acct = addon.app_payment_account.payment_account
    seller_uuid = acct.solitude_seller.uuid
    application_size = addon.current_version.all_files[0].size
    issued_at = calendar.timegm(time.gmtime())

    icons = {}
    for size in amo.ADDON_ICON_SIZES:
        icons[str(size)] = absolutify(addon.get_icon_url(size))

    token_data = {
        'iss': settings.APP_PURCHASE_KEY,
        'typ': settings.APP_PURCHASE_TYP,
        'aud': settings.APP_PURCHASE_AUD,
        'iat': issued_at,
        'exp': issued_at + 3600,  # expires in 1 hour
        'request': {
            'name': unicode(addon.name),
            'description': app_description,
            'pricePoint': addon.premium.price.name,
            'id': make_ext_id(addon.pk),
            'postbackURL': absolutify(reverse('webpay.postback')),
            'chargebackURL': absolutify(reverse('webpay.chargeback')),
            'productData': urlencode({
                'contrib_uuid': uuid_,
                'seller_uuid': seller_uuid,
                'addon_id': addon.pk,
                'application_size': application_size
            }),
            'icons': icons,
        }
    }

    token = sign_webpay_jwt(token_data)
    log.debug('Preparing webpay JWT for addon %s: %s' % (addon, token))

    return {
        'webpayJWT': token,
        'contribStatusURL': reverse('webpay-status', kwargs={'uuid': uuid_})
    }


def _prepare_pay_inapp(inapp, source=None, lang=None,
                       client_data=None):
    """
    Prepare a JWT to pass into navigator.pay() for in app purchaseable item
    """
    log.debug('Starting purchase of inapp: %s' % inapp.pk)

    # Amount is set to none becuase we can't know the user's region
    # until after the payment is complete.
    contrib = Contribution.objects.create(addon_id=inapp.webapp.id,
                                          amount=None,
                                          client_data=client_data,
                                          paykey=None,
                                          price_tier=inapp.price,
                                          source=source,
                                          source_locale=lang,
                                          type=amo.CONTRIB_PENDING,
                                          uuid=str(uuid.uuid4()))
    log.debug('Storing contrib for uuid: %s' % contrib.uuid)

    # Until atob() supports encoded HTML we are stripping all tags.
    # See bug 831524
    app_description = bleach.clean(unicode(inapp.webapp.description),
                                   strip=True, tags=[])

    acct = inapp.webapp.app_payment_account.payment_account
    seller_uuid = acct.solitude_seller.uuid
    issued_at = calendar.timegm(time.gmtime())

    # TODO: Default to 64x64 icon until addressed in
    # https://bugzilla.mozilla.org/show_bug.cgi?id=981093
    icons = {64: absolutify(inapp.logo_url)}

    token_data = {
        'iss': settings.APP_PURCHASE_KEY,
        'typ': settings.APP_PURCHASE_TYP,
        'aud': settings.APP_PURCHASE_AUD,
        'iat': issued_at,
        'exp': issued_at + 3600,  # expires in 1 hour
        'request': {
            'name': unicode(inapp.name),
            'description': app_description,
            'pricePoint': inapp.price.name,
            'id': make_ext_id_inapp(inapp.pk),
            'postbackURL': absolutify(reverse('webpay.postback')),
            'chargebackURL': absolutify(reverse('webpay.chargeback')),
            'productData': urlencode({
                'contrib_uuid': contrib.uuid,
                'seller_uuid': seller_uuid,
                'addon_id': inapp.webapp.pk,
                'inapp_id': inapp.pk,
                'application_size': None
            }),
            'icons': icons,
        }
    }

    token = sign_webpay_jwt(token_data)
    log.debug('Preparing webpay JWT for inapp %s: %s' % (inapp, token))

    return {
        'webpayJWT': token,
        'contribStatusURL': reverse('webpay-status',
                                    kwargs={'uuid': contrib.uuid})
    }


@login_required
@addon_view
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

    tasks.send_purchase_receipt.delay(contrib.pk)
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
