import hashlib
import hmac
import json
import uuid
import urlparse
from datetime import datetime

from django import http
from django.conf import settings
from django.contrib import auth
from django.contrib.auth.signals import user_logged_in
from django.core.urlresolvers import reverse
from django.db import IntegrityError
from django.http import JsonResponse
from django.utils.datastructures import MultiValueDictKeyError

import basket
import commonware.log
from django_browserid import get_audience
from django_statsd.clients import statsd

from requests_oauthlib import OAuth2Session
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, ParseError
from rest_framework.generics import (CreateAPIView, DestroyAPIView,
                                     RetrieveAPIView, RetrieveUpdateAPIView)
from rest_framework.mixins import DestroyModelMixin, ListModelMixin
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet

import mkt
from lib.metrics import record_action
from mkt.access.models import Group, GroupUser
from mkt.api.paginator import CustomPagination
from mkt.users.models import UserProfile
from mkt.users.views import browserid_authenticate

from mkt.account.serializers import (AccountSerializer, FeedbackSerializer,
                                     FxALoginSerializer, GroupsSerializer,
                                     LoginSerializer,
                                     NewsletterSerializer,
                                     PermissionsSerializer, TOSSerializer)
from mkt.api.authentication import (RestAnonymousAuthentication,
                                    RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.base import CORSMixin, MarketplaceView
from mkt.api.permissions import AllowSelf, AllowOwner, GroupPermission
from mkt.constants.apps import INSTALL_TYPE_USER
from mkt.site.mail import send_mail_jinja
from mkt.site.utils import log_cef
from mkt.webapps.serializers import SimpleAppSerializer
from mkt.webapps.models import Installed, Webapp


log = commonware.log.getLogger('z.account')


def user_relevant_apps(user):
    return {
        'developed': list(user.addonuser_set.filter(
            role=mkt.AUTHOR_ROLE_OWNER).values_list('addon_id', flat=True)),
        'installed': list(user.installed_set.values_list(
            'addon_id', flat=True)),
        'purchased': list(user.purchase_ids()),
    }


class MineMixin(object):
    def get_object(self):
        pk = self.kwargs.get('pk')
        if pk == 'mine':
            self.kwargs['pk'] = self.request.user.pk
        return super(MineMixin, self).get_object()


class InstalledViewSet(CORSMixin, MarketplaceView, ListModelMixin,
                       GenericViewSet):
    cors_allowed_methods = ['get']
    serializer_class = SimpleAppSerializer
    permission_classes = [AllowSelf]
    pagination_class = CustomPagination
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication]

    def get_queryset(self):
        return Webapp.objects.filter(
            installed__user=self.request.user,
            installed__install_type=INSTALL_TYPE_USER).order_by(
                '-installed__created')

    def remove_app(self, request, **kwargs):
        self.cors_allowed_methods = ['post']
        try:
            to_remove = Webapp.objects.get(pk=request.data['app'])
        except (KeyError, MultiValueDictKeyError):
            raise ParseError(detail='`app` was not provided.')
        except Webapp.DoesNotExist:
            raise ParseError(detail='`app` does not exist.')
        try:
            installed = request.user.installed_set.get(
                install_type=INSTALL_TYPE_USER, addon_id=to_remove.pk)
            installed.delete()
        except Installed.DoesNotExist:
            raise ParseError(detail='`app` is not installed or not removable.')
        return Response(status=status.HTTP_202_ACCEPTED)


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
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            data = self.create_action(request, serializer)
            return self.response_success(request, serializer, data=data)
        return self.response_error(request, serializer)


class AccountView(MineMixin, CORSMixin, RetrieveUpdateAPIView):
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication]
    cors_allowed_methods = ['get', 'patch', 'put']
    model = UserProfile
    queryset = UserProfile.objects.all()
    permission_classes = (AllowOwner,)
    serializer_class = AccountSerializer


class AnonymousUserMixin(object):
    def get_object(self, *args, **kwargs):
        try:
            user = super(AnonymousUserMixin, self).get_object(*args, **kwargs)
        except http.Http404:
            # The base get_object() will raise Http404 instead of DoesNotExist.
            # Treat no object as an anonymous user (source: unknown).
            user = UserProfile(is_verified=False)
        return user


class FeedbackView(CORSMixin, CreateAPIViewWithoutModel):
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication]

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
                        context_data, headers={'Reply-To': sender},
                        recipient_list=[settings.MKT_APPS_FEEDBACK_EMAIL])

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


def fxa_oauth_api(name):
    return urlparse.urljoin(settings.FXA_OAUTH_URL, 'v1/' + name)


def find_or_create_user(email, fxa_uid):

    def find_user(**kwargs):
        try:
            return UserProfile.objects.get(**kwargs)
        except UserProfile.DoesNotExist:
            return None

    profile = find_user(fxa_uid=fxa_uid) or find_user(email=email)
    if profile:
        created = False
        profile.update(fxa_uid=fxa_uid, email=email)
    else:
        created = True
        profile = UserProfile.objects.create(
            fxa_uid=fxa_uid,
            email=email,
            source=mkt.LOGIN_SOURCE_FXA,
            display_name=email.partition('@')[0],
            is_verified=True)

    if profile.source != mkt.LOGIN_SOURCE_FXA:
        log.info('Set account to FxA for {0}'.format(email))
        statsd.incr('z.mkt.user.fxa')
        profile.update(source=mkt.LOGIN_SOURCE_FXA)

    return profile, created


def fxa_authorize(session, client_secret, auth_response):
    token = session.fetch_token(
        fxa_oauth_api('token'),
        authorization_response=auth_response,
        client_secret=client_secret)
    res = session.post(
        fxa_oauth_api('verify'),
        data=json.dumps({'token': token['access_token']}),
        headers={'Content-Type': 'application/json'})
    return res.json()


class FxALoginView(CORSMixin, CreateAPIViewWithoutModel):
    authentication_classes = []
    serializer_class = FxALoginSerializer

    def create_action(self, request, serializer):
        client_id = request.POST.get('client_id', settings.FXA_CLIENT_ID)
        secret = settings.FXA_SECRETS[client_id]
        session = OAuth2Session(
            client_id,
            scope=u'profile',
            state=serializer.data['state'])

        auth_response = serializer.data['auth_response']
        fxa_authorization = fxa_authorize(session, secret, auth_response)

        if 'user' in fxa_authorization:
            email = fxa_authorization['email']
            fxa_uid = fxa_authorization['user']
            profile, created = find_or_create_user(email, fxa_uid)
            if created:
                log_cef('New Account', 5, request, username=fxa_uid,
                        signature='AUTHNOTICE',
                        msg='User created a new account (from FxA)')
                record_action('new-user', request)
            auth.login(request, profile)
            profile.update(last_login_ip=request.META.get('REMOTE_ADDR', ''))

            auth.signals.user_logged_in.send(sender=profile.__class__,
                                             request=request,
                                             user=profile)
        else:
            raise AuthenticationFailed('No profile.')

        request.user = profile
        request.groups = profile.groups.all()
        # Remember whether the user has logged in to highlight the register or
        # sign in nav button. 31536000 == one year.
        request.set_cookie('has_logged_in', '1', max_age=5 * 31536000)

        # We want to return completely custom data, not the serializer's.
        data = {
            'error': None,
            'token': commonplace_token(request.user.email),
            'settings': {
                'display_name': request.user.display_name,
                'email': request.user.email,
                'enable_recommendations': request.user.enable_recommendations,
                'source': 'firefox-accounts',
            }
        }

        context = {'request': request}

        # Serializers give up if they aren't passed an instance, so we
        # do that here despite PermissionsSerializer not needing one
        # really.
        permissions = PermissionsSerializer(context=context, instance=True)
        data.update(permissions.data)

        # Has the user signed the developer agreement?
        data['tos'] = TOSSerializer(context=context, instance=True).data

        # Add ids of installed/purchased/developed apps.
        data['apps'] = user_relevant_apps(profile)

        return data


class LoginView(CORSMixin, CreateAPIViewWithoutModel):
    authentication_classes = []
    serializer_class = LoginSerializer

    def create_action(self, request, serializer):
        with statsd.timer('auth.browserid.verify'):
            profile, msg = browserid_authenticate(
                request, serializer.data['assertion'],
                browserid_audience=(serializer.data['audience'] or
                                    get_audience(request)),
                is_mobile=serializer.data['is_mobile'],
            )
        if profile is None:
            # Authentication failure.
            log.info('No profile: %s' % (msg or ''))
            raise AuthenticationFailed('No profile.')

        request.user = profile
        request.groups = profile.groups.all()

        auth.login(request, profile)
        user_logged_in.send(sender=profile.__class__, request=request,
                            user=profile)

        # We want to return completely custom data, not the serializer's.
        data = {
            'error': None,
            'token': commonplace_token(request.user.email),
            'settings': {
                'display_name': request.user.display_name,
                'email': request.user.email,
                'enable_recommendations': request.user.enable_recommendations,
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

    def get_region(self):
        return self.request.REGION.slug

    def get_country(self):
        region = self.get_region()
        return '' if region == 'restofworld' else region

    def response_success(self, request, serializer, data=None):
        return Response({}, status=status.HTTP_204_NO_CONTENT)

    def create_action(self, request, serializer):
        email = serializer.data['email']
        newsletter = serializer.data['newsletter']
        lang = serializer.data['lang']
        country = self.get_country()
        basket.subscribe(email, newsletter, format='H', country=country,
                         lang=lang, optin='Y', trigger_welcome='Y')


class PermissionsView(CORSMixin, MineMixin, RetrieveAPIView):

    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication]
    cors_allowed_methods = ['get']
    permission_classes = (AllowSelf,)
    model = UserProfile
    queryset = UserProfile.objects.all()
    serializer_class = PermissionsSerializer


class GroupsViewSet(CORSMixin, ListModelMixin, DestroyModelMixin,
                    GenericViewSet):
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication]
    cors_allowed_methods = ['get', 'post', 'delete']
    serializer_class = GroupsSerializer
    permission_classes = [GroupPermission('Admin', '%')]

    def paginate_queryset(self, queryset, page_size=None):
        return None

    def get_queryset(self):
        return self.get_user().groups.all()

    def get_user(self):
        try:
            return UserProfile.objects.get(pk=self.kwargs.get('pk'))
        except UserProfile.DoesNotExist:
            raise ParseError('User must exist.')

    def get_group(self):
        try:
            group = (self.request.data.get('group') or
                     self.request.query_params.get('group'))
            return Group.objects.get(pk=group)
        except Group.DoesNotExist:
            raise ParseError('Group does not exist.')

    def get_object(self):
        user = self.get_user()
        group = self.get_group()
        try:
            obj = GroupUser.objects.get(user=user, group=group)
        except GroupUser.DoesNotExist, e:
            raise ParseError('User isn\'t in that group? %s' % e)
        return obj

    def perform_destroy(self, instance):
        if instance.group.restricted:
            raise ParseError('Restricted groups can\'t be unset via the API.')
        instance.delete()

    def create(self, request, **kwargs):
        user = self.get_user()
        group = self.get_group()
        if group.restricted:
            raise ParseError('Restricted groups can\'t be set via the API.')
        try:
            GroupUser.objects.create(user=user, group=group)
        except IntegrityError, e:
            raise ParseError('User is already in that group? %s' % e)

        return Response(status=status.HTTP_201_CREATED)


class TOSShowView(CORSMixin, APIView):
    """
    Viewset allowing a user to see the developer agreement. Users cannot sign
    to the agreement until they've viewed it.
    """
    allowed_methods = ['post']
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication]
    cors_allowed_methods = ['post']
    permission_classes = (IsAuthenticated,)

    def response_body(self):
        return {
            'url': reverse('mkt.developers.apps.terms_standalone')
        }

    def post(self, request):
        if request.user.shown_dev_agreement is not None:
            return Response(self.response_body(),
                            status=status.HTTP_200_OK)
        request.user.update(shown_dev_agreement=datetime.now())
        return Response(self.response_body(), status=status.HTTP_201_CREATED)


class TOSReadView(CORSMixin, APIView):
    """
    Viewset allowing a user to sign the developer agreement. Users cannot do so
    until they have previously been shown the agreement.
    """
    allowed_methods = ['post']
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication]
    cors_allowed_methods = ['post']
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        if (request.user.read_dev_agreement is not None or
                request.user.shown_dev_agreement is None):
            return Response(status=status.HTTP_400_BAD_REQUEST)
        request.user.update(read_dev_agreement=datetime.now())
        return Response(status=status.HTTP_201_CREATED)


def user_session_view(request):
    return JsonResponse({
        'has_session': request.user.is_authenticated()
    })
