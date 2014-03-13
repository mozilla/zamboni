import calendar
import time
from urllib import urlencode

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

import jwt
from nose.tools import nottest
from receipts.receipts import Receipt

from access import acl
from amo.helpers import absolutify
from amo.urlresolvers import reverse
from lib.crypto import receipt


def get_uuid(app, user):
    """
    Returns a users uuid suitable for use in the receipt, by looking up
    the purchase table. Otherwise it just returns 'none'.

    :params app: the app record.
    :params user: the UserProfile record.
    """
    try:
        return app.addonpurchase_set.get(user=user).uuid
    except ObjectDoesNotExist:
        return 'none'


def sign(data):
    """
    Returns a signed receipt. If the seperate signing server is present then
    it will use that. Otherwise just uses JWT.

    :params receipt: the receipt to be signed.
    """
    if settings.SIGNING_SERVER_ACTIVE:
        return receipt.sign(data)
    else:
        return jwt.encode(data, get_key(), u'RS512')


def create_receipt(webapp, user, uuid, flavour=None):
    """
    Creates a receipt for use in payments.

    :params app: the app record.
    :params user: the UserProfile record.
    :params uuid: a uuid placed in the user field for this purchase.
    :params flavour: None, developer or reviewer, the flavour of receipt.
    """
    assert flavour in [None, 'developer', 'reviewer'], (
        'Invalid flavour: %s' % flavour)

    time_ = calendar.timegm(time.gmtime())
    typ = 'purchase-receipt'

    product = {'storedata': urlencode({'id': int(webapp.pk)}),
               # Packaged and hosted apps should have an origin. If there
               # isn't one, fallback to the SITE_URL.
               'url': webapp.origin or settings.SITE_URL}

    # Generate different receipts for reviewers or developers.
    expiry = time_ + settings.WEBAPPS_RECEIPT_EXPIRY_SECONDS
    if flavour:
        if not (acl.action_allowed_user(user, 'Apps', 'Review') or
                webapp.has_author(user)):
            raise ValueError('User %s is not a reviewer or developer' %
                             user.pk)

        # Developer and reviewer receipts should expire after 24 hours.
        expiry = time_ + (60 * 60 * 24)
        typ = flavour + '-receipt'
        verify = absolutify(reverse('receipt.verify', args=[webapp.guid]))
    else:
        verify = settings.WEBAPPS_RECEIPT_URL

    reissue = absolutify(reverse('receipt.reissue'))
    receipt = dict(exp=expiry, iat=time_,
                   iss=settings.SITE_URL, nbf=time_, product=product,
                   # TODO: This is temporary until detail pages get added.
                   detail=absolutify(reissue),  # Currently this is a 404.
                   reissue=absolutify(reissue),
                   typ=typ,
                   user={'type': 'directed-identifier',
                         'value': uuid},
                   verify=verify)
    return sign(receipt)


def reissue_receipt(receipt):
    """
    Reissues and existing receipt by updating the timestamps and resigning
    the receipt. This requires a well formatted receipt, but does not verify
    the receipt contents.

    :params receipt: an existing receipt
    """
    time_ = calendar.timegm(time.gmtime())
    receipt_obj = Receipt(receipt)
    data = receipt_obj.receipt_decoded()
    data.update({
        'exp': time_ + settings.WEBAPPS_RECEIPT_EXPIRY_SECONDS,
        'iat': time_,
        'nbf': time_,
    })
    return sign(data)


@nottest
def create_test_receipt(root, status):
    time_ = calendar.timegm(time.gmtime())
    detail = absolutify(reverse('receipt.test.details'))
    receipt = {
        'detail': absolutify(detail),
        'exp': time_ + (60 * 60 * 24),
        'iat': time_,
        'iss': settings.SITE_URL,
        'nbf': time_,
        'product': {
            'storedata': urlencode({'id': 0}),
            'url': root,
        },
        'reissue': detail,
        'typ': 'test-receipt',
        'user': {
            'type': 'directed-identifier',
            'value': 'none'
        },
        'verify': absolutify(reverse('receipt.test.verify',
                                     kwargs={'status': status}))

    }
    return sign(receipt)


def get_key():
    """Return a key for using with encode."""
    return jwt.rsa_load(settings.WEBAPPS_RECEIPT_KEY)
