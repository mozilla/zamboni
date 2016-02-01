import string
from urllib import urlencode

from django.http import HttpResponse, HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt

import commonware.log
from oauthlib import oauth1
from oauthlib.common import safe_string_equals
from jingo.helpers import urlparams

from mkt.api.models import Access, Nonce, Token, REQUEST_TOKEN, ACCESS_TOKEN
from mkt.site.decorators import login_required
from mkt.site.utils import render


DUMMY_CLIENT_KEY = u'DummyOAuthClientKeyString'
DUMMY_REQUEST_TOKEN = u'DummyOAuthRequestToken'
DUMMY_ACCESS_TOKEN = u'DummyOAuthAccessToken'
DUMMY_SECRET = u'DummyOAuthSecret'

log = commonware.log.getLogger('z.api')


def get_request_headers(request):
    return {
        'Authorization': request.META.get('HTTP_AUTHORIZATION'),
        'Content-Type': request.META.get('CONTENT_TYPE', '')
    }


class MarketplaceOAuthRequestValidator(oauth1.RequestValidator):
    safe_characters = set(string.printable)
    nonce_length = (7, 128)
    access_token_length = (8, 128)
    request_token_length = (8, 128)
    verifier_length = (8, 128)
    client_key_length = (8, 128)
    enforce_ssl = False  # SSL enforcement is handled by ops. :-)

    def validate_client_key(self, key, request):
        request.attempted_key = key
        return Access.objects.filter(key=key).exists()

    def get_client_secret(self, key, request):
        # This method returns a dummy secret on failure so that auth
        # success and failure take a codepath with the same run time,
        # to prevent timing attacks.
        try:
            # OAuthlib needs unicode objects, django-aesfield returns a string.
            return Access.objects.get(key=key).secret.decode('utf8')
        except Access.DoesNotExist:
            return DUMMY_SECRET

    @property
    def dummy_client(self):
        return DUMMY_CLIENT_KEY

    @property
    def dummy_request_token(self):
        return DUMMY_REQUEST_TOKEN

    @property
    def dummy_access_token(self):
        return DUMMY_ACCESS_TOKEN

    def get_default_realms(self, client_key, request):
        return []

    def validate_timestamp_and_nonce(self, client_key, timestamp, nonce,
                                     request, request_token=None,
                                     access_token=None):
        n, created = Nonce.objects.safer_get_or_create(
            defaults={'client_key': client_key},
            nonce=nonce, timestamp=timestamp,
            request_token=request_token,
            access_token=access_token)
        return created

    def validate_requested_realms(self, client_key, realms, request):
        return True

    def validate_realms(self, client_key, token, request, uri=None,
                        realms=None):
        return True

    def validate_redirect_uri(self, client_key, redirect_uri, request):
        return True

    def validate_request_token(self, client_key, request_token, request):
        # This method must take the same amount of time/db lookups for
        # success and failure to prevent timing attacks.
        return Token.objects.filter(token_type=REQUEST_TOKEN,
                                    creds__key=client_key,
                                    key=request_token).exists()

    def validate_access_token(self, client_key, access_token, request):
        # This method must take the same amount of time/db lookups for
        # success and failure to prevent timing attacks.
        return Token.objects.filter(token_type=ACCESS_TOKEN,
                                    creds__key=client_key,
                                    key=access_token).exists()

    def validate_verifier(self, client_key, request_token, verifier, request):
        # This method must take the same amount of time/db lookups for
        # success and failure to prevent timing attacks.
        try:
            t = Token.objects.get(key=request_token, token_type=REQUEST_TOKEN)
            candidate = t.verifier
        except Token.DoesNotExist:
            candidate = ''
        return safe_string_equals(candidate, verifier)

    def get_request_token_secret(self, client_key, request_token, request):
        # This method must take the same amount of time/db lookups for
        # success and failure to prevent timing attacks.
        try:
            t = Token.objects.get(key=request_token, creds__key=client_key,
                                  token_type=REQUEST_TOKEN)
            return t.secret
        except Token.DoesNotExist:
            return DUMMY_SECRET

    def get_access_token_secret(self, client_key, request_token, request):
        # This method must take the same amount of time/db lookups for
        # success and failure to prevent timing attacks.
        try:
            t = Token.objects.get(key=request_token, creds__key=client_key,
                                  token_type=ACCESS_TOKEN)
        except Token.DoesNotExist:
            return DUMMY_SECRET

        return t.secret


validator = MarketplaceOAuthRequestValidator()
server = oauth1.WebApplicationServer(validator)


@csrf_exempt
def access_request(request):
    try:
        oauth_req = server._create_request(request.build_absolute_uri(),
                                           request.method, request.body,
                                           get_request_headers(request))
        valid, oauth_req = server.validate_access_token_request(oauth_req)
    except ValueError:
        valid = False
    if valid:
        req_t = Token.objects.get(
            token_type=REQUEST_TOKEN,
            key=oauth_req.resource_owner_key)
        t = Token.generate_new(
            token_type=ACCESS_TOKEN,
            creds=req_t.creds,
            user=req_t.user)
        # Clean up as we go.
        req_t.delete()
        return HttpResponse(
            urlencode({'oauth_token': t.key,
                       'oauth_token_secret': t.secret}),
            content_type='application/x-www-form-urlencoded')
    else:
        log.error('Invalid OAuth request for acquiring access token')
        return HttpResponse(status=401)


@csrf_exempt
def token_request(request):
    try:
        oauth_req = server._create_request(request.build_absolute_uri(),
                                           request.method, request.body,
                                           get_request_headers(request))
        valid, oauth_req = server.validate_request_token_request(oauth_req)
    except ValueError:
        valid = False
    if valid:
        consumer = Access.objects.get(key=oauth_req.client_key)
        t = Token.generate_new(token_type=REQUEST_TOKEN, creds=consumer)
        return HttpResponse(
            urlencode({'oauth_token': t.key,
                       'oauth_token_secret': t.secret,
                       'oauth_callback_confirmed': True}),
            content_type='application/x-www-form-urlencoded')
    else:
        log.error('Invalid OAuth request for acquiring request token')
        return HttpResponse(status=401)


@csrf_exempt
@login_required
def authorize(request):
    if request.method == 'GET' and 'oauth_token' in request.GET:
        try:
            t = Token.objects.get(token_type=REQUEST_TOKEN,
                                  key=request.GET['oauth_token'])
        except Token.DoesNotExist:
            log.error('Invalid OAuth request for obtaining user authorization')
            return HttpResponse(status=401)
        return render(request, 'developers/oauth_authorize.html',
                      {'app_name': t.creds.app_name,
                       'oauth_token': request.GET['oauth_token']})
    elif request.method == 'POST':
        token = request.POST.get('oauth_token')
        try:
            t = Token.objects.get(token_type=REQUEST_TOKEN,
                                  key=token)
        except Token.DoesNotExist:
            return HttpResponse(status=401)
        if 'grant' in request.POST:
            t.user = request.user
            t.save()
            return HttpResponseRedirect(
                urlparams(t.creds.redirect_uri, oauth_token=token,
                          oauth_verifier=t.verifier))
        elif 'deny' in request.POST:
            t.delete()
            return HttpResponse(status=200)
    else:
        log.error('Invalid OAuth request for user access authorization')
        return HttpResponse(status=401)
