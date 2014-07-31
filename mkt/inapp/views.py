import json

from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework.permissions import AllowAny
from rest_framework.viewsets import ModelViewSet

import commonware.log
from mkt.api.authentication import (RestAnonymousAuthentication,
                                    RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.authorization import AllowAuthor, ByHttpMethod
from mkt.api.base import CORSMixin, MarketplaceView
from mkt.inapp.models import InAppProduct
from mkt.inapp.serializers import InAppProductSerializer
from mkt.prices.models import Price
from mkt.webapps.models import Webapp

log = commonware.log.getLogger('z.inapp')


class InAppProductViewSet(CORSMixin, MarketplaceView, ModelViewSet):
    serializer_class = InAppProductSerializer
    cors_allowed_methods = ('get', 'post', 'put', 'patch', 'delete')
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

    def destroy(self):
        raise NotImplemented('destroy is not allowed')

    def pre_save(self, in_app_product):
        in_app_product.webapp = self.get_app()

    def get_queryset(self):
        return InAppProduct.objects.filter(webapp=self.get_app())

    def get_app(self):
        if not hasattr(self, 'app'):
            self.app = get_object_or_404(Webapp,
                                         app_domain=self.kwargs['origin'])
        return self.app

    def get_authors(self):
        return self.get_app().authors.all()


class StubInAppProductViewSet(CORSMixin, MarketplaceView, ModelViewSet):
    serializer_class = InAppProductSerializer
    cors_allowed_methods = ('get',)
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
        for name, amount in (('Kiwi', '0.99'),
                             ('Unicorn', '1.99')):
            log.info('Creating stub in-app product {n} {p}'
                     .format(n=name, p=amount))
            # TODO: make this adjustable.
            simulate = json.dumps({'result': 'postback'})
            InAppProduct.objects.create(stub=True,
                                        simulate=simulate,
                                        name=name,
                                        price=Price.objects.get(price=amount))
