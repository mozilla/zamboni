import calendar
import time
from urllib import urlencode

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse

import jwt
from nose.tools import nottest
from receipts.receipts import Receipt

from lib.crypto import receipt
from lib.utils import static_url
from mkt.access import acl
from mkt.site.helpers import absolutify


def get_uuid(app, user):
    """
    Returns a users uuid suitable for use in the receipt, by looking up
    the purchase table. Otherwise it just returns 'none'.

    :params app: the app record.
    :params user: the UserProfile record.
    """
    try:
        return app.webapppurchase_set.get(user=user).uuid
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


def create_receipt(webapp, user, uuid, flavour=None, contrib=None):
    return sign(create_receipt_data(webapp, user, uuid, flavour=flavour,
                                    contrib=contrib))


def create_receipt_data(webapp, user, uuid, flavour=None, contrib=None):
    """
    Creates receipt data for use in payments.

    :params app: the app record.
    :params user: the UserProfile record.
    :params uuid: a uuid placed in the user field for this purchase.
    :params flavour: None, developer, inapp, or reviewer - the flavour
            of receipt.
    :param: contrib: the Contribution object for the purchase.
    """
    # Unflavo(u)red receipts are for plain ol' vanilla app purchases.
    assert flavour in (None, 'developer', 'inapp', 'reviewer'), (
        'Invalid flavour: %s' % flavour)

    time_ = calendar.timegm(time.gmtime())
    typ = 'purchase-receipt'
    storedata = {'id': int(webapp.pk)}

    # Generate different receipts for reviewers or developers.
    expiry = time_ + settings.WEBAPPS_RECEIPT_EXPIRY_SECONDS
    verify = static_url('WEBAPPS_RECEIPT_URL')

    if flavour == 'inapp':
        if not contrib:
            raise ValueError(
                'a contribution object is required for in-app receipts')
        if not contrib.inapp_product:
            raise ValueError(
                'contribution {c} does not link to an in-app product'
                .format(c=contrib))
        storedata['contrib'] = int(contrib.pk)
        storedata['inapp_id'] = contrib.inapp_product.guid

    elif flavour in ('developer', 'reviewer'):
        if not (acl.action_allowed_user(user, 'Apps', 'Review') or
                webapp.has_author(user)):
            raise ValueError('User %s is not a reviewer or developer' %
                             user.pk)

        # Developer and reviewer receipts should expire after 24 hours.
        expiry = time_ + (60 * 60 * 24)
        typ = flavour + '-receipt'
        verify = absolutify(reverse('receipt.verify', args=[webapp.guid]))

    product = {'storedata': urlencode(storedata),
               # Packaged and hosted apps should have an origin. If there
               # isn't one, fallback to the SITE_URL.
               'url': webapp.origin or settings.SITE_URL}
    reissue = absolutify(reverse('receipt.reissue'))
    receipt = dict(exp=expiry, iat=time_,
                   iss=settings.SITE_URL, nbf=time_, product=product,
                   # TODO: This is temporary until detail pages get added.
                   # TODO: bug 1020997, bug 1020999
                   detail=absolutify(reissue),  # Currently this is a 404.
                   reissue=absolutify(reissue),
                   typ=typ,
                   user={'type': 'directed-identifier',
                         'value': uuid},
                   verify=verify)
    return receipt


def create_inapp_receipt(contrib):
    """
    Creates a receipt for an in-app purchase.

    :params contrib: the Contribution object for the purchase.
    """
    if contrib.is_inapp_simulation():
        storedata = {'id': 0, 'contrib': int(contrib.pk),
                     'inapp_id': contrib.inapp_product.guid}
        return create_test_receipt(settings.SITE_URL, 'ok',
                                   storedata=storedata)

    return create_receipt(contrib.webapp, None, 'anonymous-user',
                          flavour='inapp', contrib=contrib)


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
def create_test_receipt(root, status, storedata=None):
    if not storedata:
        storedata = {'id': 0}
    time_ = calendar.timegm(time.gmtime())
    detail = absolutify(reverse('receipt.test.details'))
    receipt = {
        'detail': absolutify(detail),
        'exp': time_ + (60 * 60 * 24),
        'iat': time_,
        'iss': settings.SITE_URL,
        'nbf': time_,
        'product': {
            'storedata': urlencode(storedata),
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
