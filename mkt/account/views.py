import datetime
import hashlib
import hmac
import json
import uuid

from django import http
from django.conf import settings
from django.core.signing import BadSignature, Signer
from django.contrib import auth
from django.contrib.auth.signals import user_logged_in

import basket
import commonware.log
from django_browserid import get_audience
from django_statsd.clients import statsd

from rest_framework import status
from rest_framework.decorators import (authentication_classes,
                                       permission_classes)
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.generics import (CreateAPIView, DestroyAPIView,
                                     RetrieveAPIView, RetrieveUpdateAPIView,
                                     ListAPIView)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

import amo
from mkt.users.models import UserProfile
from mkt.users.views import browserid_authenticate

from mkt.account.serializers import (AccountSerializer, AccountInfoSerializer,
                                     FeedbackSerializer, FxALoginSerializer,
                                     LoginSerializer, NewsletterSerializer,
                                     PermissionsSerializer)
from mkt.account.utils import PREVERIFY_KEY, fxa_preverify_token
from mkt.api.authentication import (RestAnonymousAuthentication,
                                    RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.authorization import AllowSelf, AllowOwner
from mkt.api.base import CORSMixin, MarketplaceView, cors_api_view
from mkt.constants.apps import INSTALL_TYPE_USER
from mkt.site.mail import send_mail_jinja
from mkt.users.views import _fxa_authorize, get_fxa_session
from mkt.webapps.serializers import SimpleAppSerializer
from mkt.webapps.models import Webapp


log = commonware.log.getLogger('z.account')


def user_relevant_apps(user):
    return {
        'developed': list(user.addonuser_set.filter(
            role=amo.AUTHOR_ROLE_OWNER).values_list('addon_id', flat=True)),
        'installed': list(user.installed_set.values_list('addon_id',
            flat=True)),
        'purchased': list(user.purchase_ids()),
    }


class MineMixin(object):
    def get_object(self, queryset=None):
        pk = self.kwargs.get('pk')
        if pk == 'mine':
            self.kwargs['pk'] = self.request.user.pk
        return super(MineMixin, self).get_object(queryset)


class InstalledView(CORSMixin, MarketplaceView, ListAPIView):
    cors_allowed_methods = ['get']
    serializer_class = SimpleAppSerializer
    permission_classes = [AllowSelf]
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication]

    def get_queryset(self):
        return Webapp.objects.no_cache().filter(
            installed__user=self.request.user,
            installed__install_type=INSTALL_TYPE_USER).order_by(
                '-installed__created')


class CreateAPIViewWithoutModel(MarketplaceView, CreateAPIView):
    """
    A base class for APIs that need to support a create-like action, but
    without being tied to a Django Model.
    """
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]
    cors_allowed_methods = ['post']
    permission_classes = (AllowAny,)

    def response_success(self, request, serializer, data=None):
        if data is None:
            data = serializer.data
        return Response(data, status=status.HTTP_201_CREATED)

    def response_error(self, request, serializer):
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.DATA)
        if serializer.is_valid():
            data = self.create_action(request, serializer)
            return self.response_success(request, serializer, data=data)
        return self.response_error(request, serializer)


class AccountView(MineMixin, CORSMixin, RetrieveUpdateAPIView):
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication]
    cors_allowed_methods = ['get', 'patch', 'put']
    model = UserProfile
    permission_classes = (AllowOwner,)
    serializer_class = AccountSerializer


class AccountInfoView(CORSMixin, RetrieveAPIView):
    permission_classes = []
    cors_allowed_methods = ['get']
    # Only select users with an FxA source, everything else will be unkown.
    queryset = UserProfile.objects.filter(source=amo.LOGIN_SOURCE_FXA)
    serializer_class = AccountInfoSerializer
    lookup_field = 'email'

    def get_object(self, *args, **kwargs):
        try:
            user = super(AccountInfoView, self).get_object(*args, **kwargs)
        except http.Http404:
            # The base get_object() will raise Http404 instead of DoesNotExist.
            # Treat no object as an anonymous user (source: unknown).
            user = UserProfile()
        return user


class FeedbackView(CORSMixin, CreateAPIViewWithoutModel):
    class FeedbackThrottle(UserRateThrottle):
        THROTTLE_RATES = {
            'user': '30/hour',
        }

    serializer_class = FeedbackSerializer
    throttle_classes = (FeedbackThrottle,)
    throttle_scope = 'user'

    def create_action(self, request, serializer):
        context_data = self.get_context_data(request, serializer)
        sender = getattr(request.user, 'email', settings.NOBODY_EMAIL)
        send_mail_jinja(u'Marketplace Feedback', 'account/email/feedback.txt',
                        context_data, from_email=sender,
                        recipient_list=[settings.MKT_FEEDBACK_EMAIL])

    def get_context_data(self, request, serializer):
        context_data = {
            'user_agent': request.META.get('HTTP_USER_AGENT', ''),
            'ip_address': request.META.get('REMOTE_ADDR', '')
        }
        context_data.update(serializer.data)
        context_data['user'] = request.user
        return context_data


def commonplace_token(email):
    unique_id = uuid.uuid4().hex

    consumer_id = hashlib.sha1(
        email + settings.SECRET_KEY).hexdigest()

    hm = hmac.new(
        unique_id + settings.SECRET_KEY,
        consumer_id, hashlib.sha512)

    return ','.join((email, hm.hexdigest(), unique_id))


class FxALoginView(CORSMixin, CreateAPIViewWithoutModel):
    authentication_classes = []
    serializer_class = FxALoginSerializer

    def create_action(self, request, serializer):
        session = get_fxa_session(state=serializer.data['state'])

        try:
            # Maybe this was a preverified login to migrate a user.
            userid = Signer().unsign(serializer.data['state'])
        except BadSignature:
            userid = None

        profile = _fxa_authorize(
            session,
            settings.FXA_CLIENT_SECRET,
            request,
            serializer.data['auth_response'],
            userid)
        if profile is None:
            raise AuthenticationFailed('No profile.')

        request.user = profile
        request.groups = profile.groups.all()
        # We want to return completely custom data, not the serializer's.
        data = {
            'error': None,
            'token': commonplace_token(request.user.email),
            'settings': {
                'display_name': request.user.display_name,
                'email': request.user.email,
                'source': 'firefox-accounts',
            }
        }
        # Serializers give up if they aren't passed an instance, so we
        # do that here despite PermissionsSerializer not needing one
        # really.
        permissions = PermissionsSerializer(context={'request': request},
                                            instance=True)
        data.update(permissions.data)

        # Add ids of installed/purchased/developed apps.
        data['apps'] = user_relevant_apps(profile)

        return data


@cors_api_view(['POST'])
@authentication_classes([RestOAuthAuthentication,
                         RestSharedSecretAuthentication])
@permission_classes([IsAuthenticated])
def fxa_preverify_view(request):
    if not request.user.is_verified:
        return Response("User's email is not verified", status=403)

    return http.HttpResponse(
        fxa_preverify_token(request.user, datetime.timedelta(minutes=10)),
        content_type='application/jwt')


def fxa_preverify_key(request):
    return http.HttpResponse(
        json.dumps({'keys': [PREVERIFY_KEY.to_dict()]}),
        content_type='application/jwk-set+json')


class LoginView(CORSMixin, CreateAPIViewWithoutModel):
    authentication_classes = []
    serializer_class = LoginSerializer

    def create_action(self, request, serializer):
        with statsd.timer('auth.browserid.verify'):
            profile, msg = browserid_authenticate(
                request, serializer.data['assertion'],
                browserid_audience=serializer.data['audience'] or
                                   get_audience(request),
                is_mobile=serializer.data['is_mobile'],
            )
        if profile is None:
            # Authentication failure.
            log.info('No profile: %s' % (msg or ''))
            raise AuthenticationFailed('No profile.')

        request.user = profile
        request.groups = profile.groups.all()

        auth.login(request, profile)
        profile.log_login_attempt(True)  # TODO: move this to the signal.
        user_logged_in.send(sender=profile.__class__, request=request,
                            user=profile)

        # We want to return completely custom data, not the serializer's.
        data = {
            'error': None,
            'token': commonplace_token(request.user.email),
            'settings': {
                'display_name': request.user.display_name,
                'email': request.user.email,
            }
        }
        # Serializers give up if they aren't passed an instance, so we
        # do that here despite PermissionsSerializer not needing one
        # really.
        permissions = PermissionsSerializer(context={'request': request},
                                            instance=True)
        data.update(permissions.data)

        # Add ids of installed/purchased/developed apps.
        data['apps'] = user_relevant_apps(profile)

        return data


class LogoutView(CORSMixin, DestroyAPIView):
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication]
    permission_classes = (IsAuthenticated,)
    cors_allowed_methods = ['delete']

    def delete(self, request):
        auth.logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class NewsletterView(CORSMixin, CreateAPIViewWithoutModel):
    class NewsletterThrottle(UserRateThrottle):
        scope = 'newsletter'
        THROTTLE_RATES = {
            'newsletter': '30/hour',
        }

    serializer_class = NewsletterSerializer
    throttle_classes = (NewsletterThrottle,)

    def response_success(self, request, serializer, data=None):
        return Response({}, status=status.HTTP_204_NO_CONTENT)

    def create_action(self, request, serializer):
        email = serializer.data['email']
        newsletter = serializer.data['newsletter']
        basket.subscribe(email, newsletter,
                         format='H', country=request.REGION.slug,
                         lang=request.LANG, optin='Y',
                         trigger_welcome='Y')


class PermissionsView(CORSMixin, MineMixin, RetrieveAPIView):

    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication]
    cors_allowed_methods = ['get']
    permission_classes = (AllowSelf,)
    model = UserProfile
    serializer_class = PermissionsSerializer
