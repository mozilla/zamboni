from rest_framework import viewsets
from rest_framework.filters import OrderingFilter

from mkt.api.authentication import (RestAnonymousAuthentication,
                                    RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.authorization import AllowReadOnly, AnyOf, GroupPermission
from mkt.api.base import CORSMixin, SlugOrIdMixin
from mkt.collections.views import CollectionImageViewSet

from .models import FeedApp, FeedItem
from .serializers import FeedAppSerializer, FeedItemSerializer


class FeedItemViewSet(CORSMixin, viewsets.ModelViewSet):
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]
    permission_classes = [AnyOf(AllowReadOnly,
                                GroupPermission('Feed', 'Curate'))]
    filter_backends = (OrderingFilter,)
    queryset = FeedItem.objects.all()
    cors_allowed_methods = ('get', 'delete', 'post', 'put')
    serializer_class = FeedItemSerializer


class FeedAppViewSet(CORSMixin, SlugOrIdMixin, viewsets.ModelViewSet):
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]
    permission_classes = [AnyOf(AllowReadOnly,
                                GroupPermission('Feed', 'Curate'))]
    filter_backends = (OrderingFilter,)
    queryset = FeedApp.objects.all()
    cors_allowed_methods = ('get', 'delete', 'post', 'put')
    serializer_class = FeedAppSerializer


class FeedAppImageViewSet(CollectionImageViewSet):
    queryset = FeedApp.objects.all()
