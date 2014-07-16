from rest_framework import generics, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.throttling import UserRateThrottle

from mkt.abuse.serializers import AppAbuseSerializer, UserAbuseSerializer
from mkt.api.authentication import (RestOAuthAuthentication,
                                    RestAnonymousAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.base import check_potatocaptcha, CORSMixin


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

    def create(self, request, *args, **kwargs):
        fail = check_potatocaptcha(request.DATA)
        if fail:
            return fail
        # Immutable? *this* *is* PYYYYTHONNNNNNNNNN!
        request.DATA._mutable = True
        if request.user.is_authenticated():
            request.DATA['reporter'] = request.user.pk
        else:
            request.DATA['reporter'] = None
        request.DATA['ip_address'] = request.META.get('REMOTE_ADDR', '')
        return super(BaseAbuseViewSet, self).create(request, *args, **kwargs)

    def post_save(self, obj, created=False):
        obj.send()


class AppAbuseViewSet(BaseAbuseViewSet):
    serializer_class = AppAbuseSerializer


class UserAbuseViewSet(BaseAbuseViewSet):
    serializer_class = UserAbuseSerializer
