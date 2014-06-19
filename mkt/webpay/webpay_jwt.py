import calendar
import time
from urllib import urlencode
from urlparse import urljoin

from django.conf import settings
from django.core.urlresolvers import reverse

import commonware.log

import amo
from amo.helpers import absolutify
from lib.crypto.webpay import sign_webpay_jwt
from mkt.webpay.utils import make_external_id, strip_tags


log = commonware.log.getLogger('z.purchase')


def get_product_jwt(product, contribution):
    """Prepare a JWT for paid products to pass into navigator.pay()"""

    issued_at = calendar.timegm(time.gmtime())
    product_data = product.product_data(contribution)
    if not product_data.get('public_id'):
        raise ValueError(
            'Cannot create JWT without a cached public_id for '
            'app {a}'.format(a=product.addon()))

    token_data = {
        'iss': settings.APP_PURCHASE_KEY,
        'typ': settings.APP_PURCHASE_TYP,
        'aud': settings.APP_PURCHASE_AUD,
        'iat': issued_at,
        'exp': issued_at + 3600,  # expires in 1 hour
        'request': {
            'id': product.external_id(),
            'name': unicode(product.name()),
            'icons': product.icons(),
            'description': strip_tags(product.description()),
            'pricePoint': product.price().name,
            'productData': urlencode(product_data),
            'chargebackURL': absolutify(reverse('webpay.chargeback')),
            'postbackURL': absolutify(reverse('webpay.postback')),
        }
    }

    token = sign_webpay_jwt(token_data)

    log.debug('Preparing webpay JWT for self.product {0}: {1}'.format(
        product.id(), token))

    return {
        'webpayJWT': token,
        'contribStatusURL': reverse(
            'webpay-status',
            kwargs={'uuid': contribution.uuid}
        )
    }


class WebAppProduct(object):
    """Binding layer to pass a web app into a JWT producer"""

    def __init__(self, webapp):
        self.webapp = webapp

    def id(self):
        return self.webapp.pk

    def external_id(self):
        return make_external_id(self.webapp)

    def name(self):
        return self.webapp.name

    def addon(self):
        return self.webapp

    def price(self):
        return self.webapp.premium.price

    def icons(self):
        icons = {}
        for size in amo.APP_ICON_SIZES:
            icons[str(size)] = absolutify(self.webapp.get_icon_url(size))

        return icons

    def description(self):
        return self.webapp.description

    def application_size(self):
        return self.webapp.current_version.all_files[0].size

    def product_data(self, contribution):
        return {
            'addon_id': self.webapp.pk,
            'application_size': self.application_size(),
            'contrib_uuid': contribution.uuid,
            'public_id': self.addon().solitude_public_id,
        }


class InAppProduct(object):
    """Binding layer to pass a in app object into a JWT producer"""

    def __init__(self, inapp):
        self.inapp = inapp

    def id(self):
        return self.inapp.pk

    def external_id(self):
        return 'inapp.{0}'.format(make_external_id(self.inapp))

    def name(self):
        return self.inapp.name

    def addon(self):
        return self.inapp.webapp

    def price(self):
        return self.inapp.price

    def icons(self):
        # TODO: Default to 64x64 icon until addressed in
        # https://bugzilla.mozilla.org/show_bug.cgi?id=981093
        return {64: absolutify(
            self.inapp.logo_url or
            urljoin(settings.MEDIA_URL, '/img/mkt/icons/rocket-64.png')
        )}

    def description(self):
        return self.inapp.webapp.description

    def application_size(self):
        # TODO: Should this be not none, and if so
        # How do we determine the size of an in app object?
        return None

    def product_data(self, contribution):
        return {
            'addon_id': self.inapp.webapp.pk,
            'inapp_id': self.inapp.pk,
            'application_size': self.application_size(),
            'contrib_uuid': contribution.uuid,
            'public_id': self.addon().solitude_public_id,
        }
