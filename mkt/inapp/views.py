import json
from urlparse import urljoin

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework.permissions import AllowAny
from rest_framework.viewsets import ModelViewSet

import commonware.log
from mkt.api.authentication import (RestAnonymousAuthentication,
                                    RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.base import CORSMixin, MarketplaceView
from mkt.api.filters import MktFilterBackend
from mkt.api.permissions import AllowAuthor, ByHttpMethod
from mkt.inapp.models import InAppProduct
from mkt.inapp.serializers import InAppProductSerializer
from mkt.prices.models import Price
from mkt.site.helpers import absolutify
from mkt.webapps.models import Webapp

log = commonware.log.getLogger('z.inapp')


class InAppProductViewSet(CORSMixin, MarketplaceView, ModelViewSet):
    serializer_class = InAppProductSerializer
    cors_allowed_methods = ('get', 'post', 'put', 'patch', 'delete')
    cors_allowed_headers = ('content-type', 'accept', 'x-fxpay-version')
    lookup_field = 'guid'
    permission_classes = [ByHttpMethod({
        'options': AllowAny,  # Needed for CORS.
        'get': AllowAny,
        'post': AllowAuthor,
        'put': AllowAuthor,
        'patch': AllowAuthor,
    })]
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]
    filter_backends = (MktFilterBackend,)
    filter_fields = filter_munge = ('active',)

    def destroy(self):
        raise NotImplemented('destroy is not allowed')

    def pre_save(self, in_app_product):
        in_app_product.webapp = self.get_app()

    def get_queryset(self):
        return InAppProduct.objects.filter(webapp=self.get_app())

    def get_app(self):
        origin = self.kwargs['origin']
        if not hasattr(self, 'app'):
            if origin.startswith('marketplace:'):
                lookup = dict(guid=origin.replace('marketplace:', '', 1))
            else:
                lookup = dict(app_domain=origin)
            self.app = get_object_or_404(Webapp, **lookup)
        return self.app

    def get_authors(self):
        return self.get_app().authors.all()


class StubInAppProductViewSet(CORSMixin, MarketplaceView, ModelViewSet):
    serializer_class = InAppProductSerializer
    lookup_field = 'guid'
    cors_allowed_methods = ('get',)
    cors_allowed_headers = ('content-type', 'accept', 'x-fxpay-version')
    allowed_methods = ('GET',)
    permission_classes = [AllowAny]
    authentication_classes = []

    def _queryset(self):
        return InAppProduct.objects.filter(stub=True)

    def get_queryset(self):
        qs = self._queryset()
        # Since caching count() is unreliable, this optimizes for the case of
        # having already created stub products.
        if not len(qs):
            with transaction.atomic():
                self._create_stub_products()
            qs = self._queryset()
        return qs

    def _create_stub_products(self):
        for name, amount, img in (
                ('Kiwi', '0.99', 'img/developers/simulated-kiwi.png'),
                ('Rocket', '1.99', 'img/mkt/icons/rocket-64.png')):
            log.info('Creating stub in-app product {n} {p}'
                     .format(n=name, p=amount))
            # TODO: make this adjustable.
            simulate = json.dumps({'result': 'postback'})
            InAppProduct.objects.create(
                logo_url=absolutify(urljoin(settings.MEDIA_URL, img)),
                name=name,
                price=Price.objects.get(price=amount),
                simulate=simulate,
                stub=True)
