from django import http
from django.conf import settings
from django.contrib import auth
from django.utils.http import is_safe_url

import commonware.log
from django_browserid import BrowserIDBackend, get_audience
from django.utils.translation import ugettext as _

import mkt
from lib.metrics import record_action
from mkt.site.decorators import json_view, login_required
from mkt.site.utils import escape_all, log_cef

from .models import UserProfile
from .signals import logged_out


log = commonware.log.getLogger('z.users')


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

    source = mkt.LOGIN_SOURCE_MMO_BROWSERID
    display_name = email.partition('@')[0]
    profile = UserProfile.objects.create(
        email=email, source=source, display_name=display_name,
        is_verified=verified)
    log_cef('New Account', 5, request, username=display_name,
            signature='AUTHNOTICE',
            msg='User created a new account (from Persona)')
    record_action('new-user', request)

    return profile, None


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
    # Remember whether the user has logged in to highlight the register or
    # sign in nav button. 31536000 == one year.
    response.set_cookie('has_logged_in', '1', max_age=5 * 31536000)
    # Fire logged out signal.
    logged_out.send(None, request=request, response=response)
    return response
