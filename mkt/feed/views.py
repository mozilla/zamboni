from rest_framework import viewsets

from mkt.api.authentication import (RestAnonymousAuthentication,
                                    RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.authorization import AllowReadOnly, AnyOf, GroupPermission
from mkt.api.base import CORSMixin

from .models import FeedApp, FeedItem
from .serializers import FeedAppSerializer, FeedItemSerializer


class FeedItemViewSet(CORSMixin, viewsets.ModelViewSet):
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]
    permission_classes = [AnyOf(AllowReadOnly,
                                GroupPermission('Feed', 'Curate'))]
    queryset = FeedItem.objects.all()
    cors_allowed_methods = ('get', 'post')
    serializer_class = FeedItemSerializer


class FeedAppViewSet(CORSMixin, viewsets.ModelViewSet):
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]
    permission_classes = [AnyOf(AllowReadOnly,
                                GroupPermission('Feed', 'Curate'))]
    queryset = FeedApp.objects.all()
    cors_allowed_methods = ('get', 'post')
    serializer_class = FeedAppSerializer
