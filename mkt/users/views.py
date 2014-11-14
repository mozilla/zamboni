import functools

from django import http
from django.conf import settings
from django.contrib import auth
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.utils.http import is_safe_url
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

import commonware.log
import waffle
from django_browserid import BrowserIDBackend, get_audience
from django_statsd.clients import statsd
from tower import ugettext as _

import amo
from amo.utils import escape_all, log_cef
from lib.metrics import record_action
from mkt.site.decorators import json_view, login_required

from .models import UserProfile
from .signals import logged_out
from .utils import autocreate_username


log = commonware.log.getLogger('z.users')


def user_view(f):
    @functools.wraps(f)
    def wrapper(request, user_id, *args, **kw):
        """Provides a user object given a user ID or username."""
        if user_id.isdigit():
            key = 'id'
        else:
            key = 'username'
            # If the username is `me` then show the current user's profile.
            if (user_id == 'me' and request.user.is_authenticated() and
                request.user.username):
                user_id = request.user.username
        user = get_object_or_404(UserProfile, **{key: user_id})
        return f(request, user, *args, **kw)
    return wrapper


@login_required(redirect=False)
@json_view
def ajax(request):
    """Query for a user matching a given email."""

    if 'q' not in request.GET:
        raise http.Http404()

    data = {'status': 0, 'message': ''}

    email = request.GET.get('q', '').strip()
    dev_only = request.GET.get('dev', '1')
    try:
        dev_only = int(dev_only)
    except ValueError:
        dev_only = 1

    if not email:
        data.update(message=_('An email address is required.'))
        return data

    user = UserProfile.objects.filter(email=email)
    if dev_only:
        user = user.exclude(read_dev_agreement=None)

    msg = _('A user with that email address does not exist.')
    msg_dev = _('A user with that email address does not exist, or the user '
                'has not yet accepted the developer agreement.')

    if user:
        data.update(status=1, id=user[0].id, name=user[0].name)
    else:
        data['message'] = msg_dev if dev_only else msg

    return escape_all(data)


def _clean_next_url(request):
    gets = request.GET.copy()
    url = gets.get('to', settings.LOGIN_REDIRECT_URL)

    if not is_safe_url(url, host=request.get_host()):
        log.info(u'Unsafe redirect to %s' % url)
        url = settings.LOGIN_REDIRECT_URL

    gets['to'] = url
    request.GET = gets
    return request


def browserid_authenticate(request, assertion, is_mobile=False,
                           browserid_audience=get_audience):
    """
    Verify a BrowserID login attempt. If the BrowserID assertion is
    good, but no account exists, create one.

    """
    extra_params = {}
    url = settings.NATIVE_FXA_VERIFICATION_URL
    log.debug('Verifying Native FxA at %s, audience: %s, '
              'extra_params: %s' % (url, browserid_audience, extra_params))
    v = BrowserIDBackend().get_verifier()
    v.verification_service_url = url
    result = v.verify(assertion, browserid_audience, url=url, **extra_params)
    if not result:
        return None, _('Native FxA authentication failure.')

    if 'unverified-email' in result._response:
        email = result._response['unverified-email']
        verified = False
    elif (result._response.get('issuer') == settings.NATIVE_FXA_ISSUER and
          'fxa-verifiedEmail' in result._response.get('idpClaims', {})):
        email = result._response['idpClaims']['fxa-verifiedEmail']
        verified = True
    else:
        email = result.email
        verified = True

    try:
        profile = UserProfile.objects.filter(email=email)[0]
    except IndexError:
        profile = None

    if profile:
        if profile.is_verified and not verified:
            # An attempt to log in to a verified address with an unverified
            # assertion is a very bad thing. Don't let that happen.
            log.debug('Verified user %s attempted to log in with an '
                      'unverified assertion!' % profile)
            return None, _('Please use the verified email for this account.')
        else:
            profile.is_verified = verified
            profile.save()

        return profile, None

    username = autocreate_username(email.partition('@')[0])
    source = amo.LOGIN_SOURCE_MMO_BROWSERID
    profile = UserProfile.objects.create(username=username, email=email,
                                         source=source, display_name=username,
                                         is_verified=verified)
    log_cef('New Account', 5, request, username=username,
            signature='AUTHNOTICE',
            msg='User created a new account (from Persona)')
    record_action('new-user', request)

    return profile, None


@csrf_exempt
@require_POST
@transaction.commit_on_success
def browserid_login(request, browserid_audience=None):
    msg = ''
    if request.user.is_authenticated():
        # If username is different, maybe sign in as new user?
        return http.HttpResponse(status=200)
    try:
        is_mobile = bool(int(request.POST.get('is_mobile', 0)))
    except ValueError:
        is_mobile = False
    with statsd.timer('auth.browserid.verify'):
        profile, msg = browserid_authenticate(
            request, request.POST.get('assertion'),
            is_mobile=is_mobile,
            browserid_audience=browserid_audience or get_audience(request))
    if profile is not None:
        auth.login(request, profile)
        profile.log_login_attempt(True)
        return http.HttpResponse(status=200)
    return http.HttpResponse(msg, status=401)


# Used by mkt.developers.views:login.
def _login(request, template=None, data=None, dont_redirect=False):
    data = data or {}
    data['webapp'] = True
    if 'to' in request.GET:
        request = _clean_next_url(request)
    data['to'] = request.GET.get('to')

    if request.user.is_authenticated():
        return http.HttpResponseRedirect(
            request.GET.get('to', settings.LOGIN_REDIRECT_URL))

    return TemplateResponse(request, template, data)


def logout(request):
    user = request.user
    if not user.is_anonymous():
        log.debug(u"User (%s) logged out" % user)

    auth.logout(request)

    if 'to' in request.GET:
        request = _clean_next_url(request)

    next = request.GET.get('to')
    if not next:
        next = settings.LOGOUT_REDIRECT_URL
    response = http.HttpResponseRedirect(next)
    # Fire logged out signal.
    logged_out.send(None, request=request, response=response)
    return response
