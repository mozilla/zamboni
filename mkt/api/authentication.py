from django.contrib.auth.models import AnonymousUser

import commonware.log
from rest_framework.authentication import BaseAuthentication


log = commonware.log.getLogger('z.api')


class OAuthError(RuntimeError):
    def __init__(self, message='OAuth error occured.'):
        self.message = message


class RestOAuthAuthentication(BaseAuthentication):

    def authenticate(self, request):
        # Most of the work here is in the RestOAuthMiddleware.
        if (request._request.user.is_authenticated() and
                'RestOAuth' in getattr(request._request, 'authed_from', [])):
            request.user = request._request.user
            return request.user, None


class RestSharedSecretAuthentication(BaseAuthentication):

    def authenticate(self, request):
        # Most of the work here is in the RestSharedSecretMiddleware.
        if (request._request.user.is_authenticated() and
            'RestSharedSecret' in getattr(
                request._request, 'authed_from', [])):
            request.user = request._request.user
            return request.user, None


class RestAnonymousAuthentication(BaseAuthentication):

    def authenticate(self, request):
        return AnonymousUser(), None
