from django.shortcuts import get_object_or_404

from rest_framework.permissions import AllowAny
from rest_framework.viewsets import ModelViewSet

from mkt.api.authentication import (RestAnonymousAuthentication,
                                    RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.authorization import AllowAuthor, ByHttpMethod
from mkt.api.base import CORSMixin, MarketplaceView
from mkt.inapp.models import InAppProduct
from mkt.inapp.serializers import InAppProductSerializer
from mkt.webapps.models import Webapp


class InAppProductViewSet(CORSMixin, MarketplaceView, ModelViewSet):
    serializer_class = InAppProductSerializer
    cors_allowed_methods = ('get', 'post', 'put', 'patch' 'delete')
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
