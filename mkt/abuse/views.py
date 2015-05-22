from rest_framework import generics, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.throttling import UserRateThrottle

from mkt.abuse.serializers import (AppAbuseSerializer, UserAbuseSerializer,
                                   WebsiteAbuseSerializer)
from mkt.api.authentication import (RestOAuthAuthentication,
                                    RestAnonymousAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.base import CORSMixin


class AbuseThrottle(UserRateThrottle):
    THROTTLE_RATES = {
        'user': '30/hour',
    }


class BaseAbuseViewSet(CORSMixin, generics.CreateAPIView,
                       viewsets.GenericViewSet):
    cors_allowed_methods = ['post']
    throttle_classes = (AbuseThrottle,)
    throttle_scope = 'user'
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]
    permission_classes = (AllowAny,)

    def post_save(self, obj, created=False):
        obj.send()


class AppAbuseViewSet(BaseAbuseViewSet):
    serializer_class = AppAbuseSerializer


class UserAbuseViewSet(BaseAbuseViewSet):
    serializer_class = UserAbuseSerializer


class WebsiteAbuseViewSet(BaseAbuseViewSet):
    serializer_class = WebsiteAbuseSerializer
