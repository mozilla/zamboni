import calendar
import time
from urllib import urlencode
from urlparse import urljoin

from django.conf import settings
from django.core.urlresolvers import reverse

import commonware.log

import mkt
from lib.crypto.webpay import sign_webpay_jwt
from mkt.site.helpers import absolutify
from mkt.translations.models import Translation
from mkt.webpay.utils import make_external_id, strip_tags


log = commonware.log.getLogger('z.purchase')


def get_product_jwt(product, contribution):
    """
    Prepare a JWT describing the item about to be purchased when
    working with navigator.mozPay().

    See the MDN docs for details on the JWT fields:
    https://developer.mozilla.org/en-US/Marketplace/Monetization
        /In-app_payments_section/mozPay_iap
    """

    issued_at = calendar.timegm(time.gmtime())
    product_data = product.product_data(contribution)
    simulation = product.simulation()
    if not simulation and not product_data.get('public_id'):
        raise ValueError(
            'Cannot create JWT without a cached public_id for '
            'app {a}'.format(a=product.webapp()))

    token_data = {
        'iss': settings.APP_PURCHASE_KEY,
        'typ': settings.APP_PURCHASE_TYP,
        'aud': settings.APP_PURCHASE_AUD,
        'iat': issued_at,
        'exp': issued_at + 3600,  # expires in 1 hour
        'request': {
            'id': product.external_id(),
            'name': unicode(product.name()),
            'defaultLocale': product.default_locale(),
            'locales': product.localized_properties(),
            'icons': product.icons(),
            'description': strip_tags(product.description()),
            'pricePoint': product.price().name,
            'productData': urlencode(product_data),
            'chargebackURL': absolutify(reverse('webpay.chargeback')),
            'postbackURL': absolutify(reverse('webpay.postback')),
        }
    }
    if simulation:
        token_data['request']['simulate'] = simulation

    token = sign_webpay_jwt(token_data)

    log.debug('Preparing webpay JWT for product {p}, contrib {c}: {t}'
              .format(p=product.id(), t=token_data, c=contribution))

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
        self._webapp = webapp

    def id(self):
        return self._webapp.pk

    def external_id(self):
        return make_external_id(self._webapp)

    def name(self):
        return self._webapp.name

    def default_locale(self):
        return self._webapp.default_locale

    def localized_properties(self):
        props = {}

        for attr in ('name', 'description'):
            tr_object = getattr(self._webapp, attr)
            for tr in Translation.objects.filter(id=tr_object.id):
                props.setdefault(tr.locale, {})
                props[tr.locale][attr] = tr.localized_string

        return props

    def webapp(self):
        return self._webapp

    def simulation(self):
        return None

    def price(self):
        return self._webapp.premium.price

    def icons(self):
        icons = {}
        for size in mkt.CONTENT_ICON_SIZES:
            icons[str(size)] = absolutify(self._webapp.get_icon_url(size))

        return icons

    def description(self):
        return self._webapp.description

    def application_size(self):
        return self._webapp.current_version.all_files[0].size

    def product_data(self, contribution):
        data = {
            'webapp_id': self._webapp.pk,
            'application_size': self.application_size(),
            'contrib_uuid': contribution.uuid,
            'public_id': self.webapp().solitude_public_id,
        }
        if contribution.user:
            data['buyer_email'] = contribution.user.email

        return data


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

    def default_locale(self):
        # TODO: implement localization for in-app products. bug 972886
        return None

    def localized_properties(self):
        # TODO: implement localization for in-app products. bug 972886
        return {}

    def webapp(self):
        return self.inapp.webapp

    def simulation(self):
        return None

    def price(self):
        return self.inapp.price

    def icons(self):
        # TODO: Default to 64x64 icon until addressed in
        # https://bugzilla.mozilla.org/show_bug.cgi?id=981093
        return {64: absolutify(
            self.inapp.logo_url or
            urljoin(settings.MEDIA_URL, 'img/mkt/icons/rocket-64.png')
        )}

    def description(self):
        # FIXME: return in-app product description. Bug 972886.
        return self.inapp.webapp.description

    def application_size(self):
        # TODO: Should this be not none, and if so
        # How do we determine the size of an in app object?
        return None

    def product_data(self, contribution):
        return {
            'webapp_id': self.inapp.webapp.pk,
            'inapp_id': self.inapp.pk,
            'application_size': self.application_size(),
            'contrib_uuid': contribution.uuid,
            'public_id': self.webapp().solitude_public_id,
        }


class SimulatedInAppProduct(InAppProduct):

    def __init__(self, *args, **kw):
        super(SimulatedInAppProduct, self).__init__(*args, **kw)
        if not self.inapp.simulate:
            raise ValueError('This product cannot be simulated')

    def webapp(self):
        return None

    def description(self):
        # Simulated products currently do not have descriptions.
        # This cannot be blank though.
        return 'This is a stub product for testing only'

    def simulation(self):
        return self.inapp.simulate_data()

    def product_data(self, contribution):
        return {
            'inapp_id': self.inapp.pk,
            'contrib_uuid': contribution.uuid,
            'application_size': self.application_size(),
        }
