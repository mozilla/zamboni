from django.utils.datastructures import MultiValueDictKeyError

from rest_framework import response, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ParseError
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response

from mkt.api.authentication import (RestAnonymousAuthentication,
                                    RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.authorization import AllowReadOnly, AnyOf, GroupPermission
from mkt.api.base import CORSMixin, MarketplaceView, SlugOrIdMixin
from mkt.collections.views import CollectionImageViewSet
from mkt.webapps.models import Webapp

from .authorization import FeedAuthorization
from .models import FeedApp, FeedBrand, FeedItem
from .serializers import (FeedAppSerializer, FeedBrandSerializer,
                          FeedItemSerializer)


class BaseCollectionViewSet(CORSMixin, SlugOrIdMixin, MarketplaceView,
                        viewsets.ModelViewSet):
    serializer_class = None
    queryset = None
    cors_allowed_methods = ('get', 'post', 'delete', 'patch', 'put')
    permission_classes = [FeedAuthorization]
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]

    exceptions = {
        'not_provided': '`apps` was not provided.',
        'doesnt_exist': 'One or more of the specific `apps` do not exist.',
    }

    @action()
    def set_apps(self, request, *args, **kwargs):
        """
        TODO: this
        """
        collection = self.get_object()
        try:
            collection.set_apps(request.DATA['apps'])
        except (KeyError, MultiValueDictKeyError):
            raise ParseError(detail=self.exceptions['not_provided'])
        except Webapp.DoesNotExist:
            raise ParseError(detail=self.exceptions['doesnt_exist'])
        return Response(self.get_serializer(instance=collection).data,
                        status=status.HTTP_200_OK)


class FeedItemViewSet(CORSMixin, viewsets.ModelViewSet):
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]
    permission_classes = [AnyOf(AllowReadOnly,
                                GroupPermission('Feed', 'Curate'))]
    filter_backends = (OrderingFilter,)
    queryset = FeedItem.objects.all()
    cors_allowed_methods = ('get', 'delete', 'post', 'put', 'patch')
    serializer_class = FeedItemSerializer


class FeedAppViewSet(CORSMixin, MarketplaceView, SlugOrIdMixin,
                     viewsets.ModelViewSet):
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]
    permission_classes = [AnyOf(AllowReadOnly,
                                GroupPermission('Feed', 'Curate'))]
    filter_backends = (OrderingFilter,)
    queryset = FeedApp.objects.all()
    cors_allowed_methods = ('get', 'delete', 'post', 'put', 'patch')
    serializer_class = FeedAppSerializer

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(
            self.filter_queryset(self.get_queryset()))
        serializer = self.get_pagination_serializer(page)
        print serializer.data
        return response.Response(serializer.data)


class FeedAppImageViewSet(CollectionImageViewSet):
    queryset = FeedApp.objects.all()


class FeedBrandViewSet(BaseCollectionViewSet):
    serializer_class = FeedBrandSerializer
    queryset = FeedBrand.objects.all()
