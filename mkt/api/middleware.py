import hashlib
import hmac
import re
import time
from urllib import urlencode

from django.conf import settings
from django.contrib.auth.middleware import (AuthenticationMiddleware as
                                            BaseAuthenticationMiddleware)
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.middleware.gzip import GZipMiddleware as BaseGZipMiddleware
from django.utils.cache import patch_vary_headers

import commonware.log
from django_statsd.clients import statsd
from django_statsd.middleware import (GraphiteRequestTimingMiddleware,
                                      TastyPieRequestTimingMiddleware)
from multidb.pinning import (pin_this_thread, this_thread_is_pinned,
                             unpin_this_thread)
from multidb.middleware import PinningRouterMiddleware
from oauthlib.common import Request
from oauthlib.oauth1.rfc5849 import signature

from mkt.api.models import Access, ACCESS_TOKEN, Token
from mkt.api.oauth import server, validator
from mkt.carriers import get_carrier
from mkt.users.models import UserProfile


log = commonware.log.getLogger('z.api')


class RestOAuthMiddleware(object):
    """
    This is based on https://github.com/amrox/django-tastypie-two-legged-oauth
    with permission.
    """

    def process_request(self, request):
        # For now we only want these to apply to the API.
        # This attribute is set in APIBaseMiddleware.
        if not getattr(request, 'API', False):
            return

        if not settings.SITE_URL:
            raise ValueError('SITE_URL is not specified')

        # Set up authed_from attribute.
        if not hasattr(request, 'authed_from'):
            request.authed_from = []

        auth_header_value = request.META.get('HTTP_AUTHORIZATION')

        # If there is a mkt-shared-secret in the auth header, ignore it.
        if (auth_header_value and
                auth_header_value.split(None, 1)[0] == 'mkt-shared-secret'):
            log.info('mkt-shared-secret found, ignoring.')
            return

        if (not auth_header_value and
                'oauth_token' not in request.META['QUERY_STRING']):
            self.user = AnonymousUser()
            log.info('No HTTP_AUTHORIZATION header')
            return

        # Set up authed_from attribute.
        auth_header = {'Authorization': auth_header_value}
        method = getattr(request, 'signed_method', request.method)
        if ('oauth_token' in request.META['QUERY_STRING'] or
                'oauth_token' in auth_header_value):
            # This is 3-legged OAuth.
            log.info('Trying 3 legged OAuth')
            try:
                valid, oauth_req = server.validate_protected_resource_request(
                    request.build_absolute_uri(),
                    http_method=method,
                    body=request.body,
                    headers=auth_header)
            except ValueError:
                log.warning('ValueError on verifying_request', exc_info=True)
                return
            if not valid:
                log.warning(u'Cannot find APIAccess token with that key: %s'
                            % oauth_req.attempted_key)
                return
            uid = Token.objects.filter(
                token_type=ACCESS_TOKEN,
                key=oauth_req.resource_owner_key).values_list(
                    'user_id', flat=True)[0]
            request.user = UserProfile.objects.select_related(
                'user').get(pk=uid)
        else:
            # This is 2-legged OAuth.
            log.info('Trying 2 legged OAuth')
            try:
                client_key = validate_2legged_oauth(
                    server,
                    request.build_absolute_uri(),
                    method, auth_header)
            except TwoLeggedOAuthError, e:
                log.warning(str(e))
                return
            except ValueError:
                log.warning('ValueError on verifying_request', exc_info=True)
                return
            uid = Access.objects.filter(
                key=client_key).values_list(
                    'user_id', flat=True)[0]
            request.user = UserProfile.objects.select_related(
                'user').get(pk=uid)

        # But you cannot have one of these roles.
        denied_groups = set(['Admins'])
        roles = set(request.user.groups.values_list('name', flat=True))
        if roles and roles.intersection(denied_groups):
            log.info(u'Attempt to use API with denied role, user: %s'
                     % request.user.pk)
            # Set request user back to Anonymous.
            request.user = AnonymousUser()
            return

        if request.user.is_authenticated():
            request.authed_from.append('RestOAuth')

        log.info('Successful OAuth with user: %s' % request.user)


class TwoLeggedOAuthError(Exception):
    pass


def validate_2legged_oauth(oauth, uri, method, auth_header):
    """
    "Two-legged" OAuth authorization isn't standard and so not
    supported by current versions of oauthlib. The implementation
    here is sufficient for simple developer tools and testing. Real
    usage of OAuth will always require directing the user to the
    authorization page so that a resource-owner token can be
    generated.
    """
    req = Request(uri, method, '', auth_header)
    typ, params, oauth_params = oauth._get_signature_type_and_params(req)
    oauth_params = dict(oauth_params)
    req.params = filter(lambda x: x[0] not in ("oauth_signature", "realm"),
                        params)
    req.signature = oauth_params.get('oauth_signature')
    req.client_key = oauth_params.get('oauth_consumer_key')
    req.nonce = oauth_params.get('oauth_nonce')
    req.timestamp = oauth_params.get('oauth_timestamp')
    if oauth_params.get('oauth_signature_method').lower() != 'hmac-sha1':
        raise TwoLeggedOAuthError(u'unsupported signature method ' +
                                  oauth_params.get('oauth_signature_method'))
    secret = validator.get_client_secret(req.client_key, req)
    valid_signature = signature.verify_hmac_sha1(req, secret, None)
    if valid_signature:
        return req.client_key
    else:
        raise TwoLeggedOAuthError(
            u'Cannot find APIAccess token with that key: %s'
            % req.client_key)


class RestSharedSecretMiddleware(object):

    def process_request(self, request):
        # For now we only want these to apply to the API.
        # This attribute is set in APIBaseMiddleware.
        if not getattr(request, 'API', False):
            return
        # Set up authed_from attribute.
        if not hasattr(request, 'authed_from'):
            request.authed_from = []

        header = request.META.get('HTTP_AUTHORIZATION', '').split(None, 1)
        if header and header[0].lower() == 'mkt-shared-secret':
            auth = header[1]
        else:
            auth = request.GET.get('_user')
        if not auth:
            log.info('API request made without shared-secret auth token')
            return
        try:
            email, hm, unique_id = str(auth).split(',')
            consumer_id = hashlib.sha1(
                email + settings.SECRET_KEY).hexdigest()
            matches = hmac.new(unique_id + settings.SECRET_KEY,
                               consumer_id, hashlib.sha512).hexdigest() == hm
            if matches:
                try:
                    request.user = UserProfile.objects.get(email=email)
                    request.authed_from.append('RestSharedSecret')
                except UserProfile.DoesNotExist:
                    log.info('Auth token matches absent user (%s)' % email)
                    return
            else:
                log.info('Shared-secret auth token does not match')
                return

            log.info('Successful SharedSecret with user: %s' % request.user.pk)
            return
        except Exception, e:
            log.info('Bad shared-secret auth data: %s (%s)', auth, e)
            return


# How long to set the time-to-live on the cache.
PINNING_SECONDS = int(getattr(settings, 'MULTIDB_PINNING_SECONDS', 15))


class APIPinningMiddleware(PinningRouterMiddleware):
    """
    Similar to multidb, but we can't rely on cookies. Instead we cache the
    users who are to be pinned with a cache timeout. Users who are to be
    pinned are those that are not anonymous users and who are either making
    an updating request or who are already in our cache as having done one
    recently.

    If not in the API, will fall back to the cookie pinning middleware.

    Note: because the authentication process happens late when we are in the
    API, process_request() will be manually called from authentication classes
    when a user is successfully authenticated by one of those classes.
    """

    def cache_key(self, request):
        """Returns cache key based on user ID."""
        return u'api-pinning:%s' % request.user.id

    def process_request(self, request):
        if not getattr(request, 'API', False):
            return super(APIPinningMiddleware, self).process_request(request)

        if (request.user and not request.user.is_anonymous() and
                (cache.get(self.cache_key(request)) or
                 request.method in ['DELETE', 'PATCH', 'POST', 'PUT'])):
            statsd.incr('api.db.pinned')
            pin_this_thread()
            return

        statsd.incr('api.db.unpinned')
        unpin_this_thread()

    def process_response(self, request, response):
        if not getattr(request, 'API', False):
            return (super(APIPinningMiddleware, self)
                    .process_response(request, response))

        response['API-Pinned'] = str(this_thread_is_pinned())

        if (request.user and not request.user.is_anonymous() and (
                request.method in ['DELETE', 'PATCH', 'POST', 'PUT'] or
                getattr(response, '_db_write', False))):
            cache.set(self.cache_key(request), 1, PINNING_SECONDS)

        return response


class CORSMiddleware(object):

    def process_response(self, request, response):
        # This is mostly for use by tastypie. Which doesn't really have a nice
        # hook for figuring out if a response should have the CORS headers on
        # it. That's because it will often error out with immediate HTTP
        # responses.
        response['Access-Control-Allow-Headers'] = ', '.join(
            getattr(request, 'CORS_HEADERS',
                    ('X-HTTP-Method-Override', 'Content-Type')))

        error_allowed_methods = []
        if response.status_code >= 300 and request.API:
            error_allowed_methods = [request.method]

        cors_allowed_methods = getattr(request, 'CORS', error_allowed_methods)
        if cors_allowed_methods:
            response['Access-Control-Allow-Origin'] = '*'
            methods = [h.upper() for h in cors_allowed_methods]
            if 'OPTIONS' not in methods:
                methods.append('OPTIONS')
            response['Access-Control-Allow-Methods'] = ', '.join(methods)

        # The headers that the response will be able to access.
        response['Access-Control-Expose-Headers'] = (
            'API-Filter, API-Status, API-Version')

        return response

v_re = re.compile('^/api/v(?P<version>\d+)/|^/api/|^/api$')


def detect_api_version(request):
    url = request.META.get('PATH_INFO', '')
    version = v_re.match(url).group('version')
    if not version:
        version = 1
    return version


class APIBaseMiddleware(object):
    """
    Detects if this is an API call, and figures out what version of the API
    they are on. Maybe adds in a deprecation notice.
    """

    def get_api(self, request):
        if not hasattr(request, 'API'):
            request.API = False
            prefix, _, _ = request.get_full_path().lstrip('/').partition('/')
            if prefix.lower() == 'api':
                request.API = True
        return request.API

    def process_request(self, request):
        if self.get_api(request):
            version = detect_api_version(request)
            request.API_VERSION = int(version)

    def process_response(self, request, response):
        if not self.get_api(request):
            return response
        version = getattr(request, 'API_VERSION', None)
        if version is None:
            version = detect_api_version(request)
        response['API-Version'] = version
        if version < settings.API_CURRENT_VERSION:
            response['API-Status'] = 'Deprecated'
        return response


class APIFilterMiddleware(object):
    """
    Add an API-Filter header containing a urlencoded string of filters applied
    to API requests.
    """

    def process_response(self, request, response):
        if getattr(request, 'API', False) and response.status_code < 500:
            devices = []
            for device in ('GAIA', 'TV', 'MOBILE', 'TABLET'):
                if getattr(request, device, False):
                    devices.append(device.lower())
            filters = (
                ('carrier', get_carrier() or ''),
                ('device', devices),
                ('lang', request.LANG),
                ('pro', request.GET.get('pro', '')),
                ('region', request.REGION.slug),
            )
            response['API-Filter'] = urlencode(filters, doseq=True)
            patch_vary_headers(response, ['API-Filter'])
        return response


class TimingMiddleware(GraphiteRequestTimingMiddleware):
    """
    A wrapper around django_statsd timing middleware that sends different
    statsd pings if being used in API.
    """

    def process_view(self, request, *args):
        if getattr(request, 'API', False):
            TastyPieRequestTimingMiddleware().process_view(request, *args)
        else:
            super(TimingMiddleware, self).process_view(request, *args)

    def _record_time(self, request):
        pre = 'api' if getattr(request, 'API', False) else 'view'
        if hasattr(request, '_start_time'):
            ms = int((time.time() - request._start_time) * 1000)
            data = {'method': request.method,
                    'module': request._view_module,
                    'name': request._view_name,
                    'pre': pre}
            statsd.timing('{pre}.{module}.{name}.{method}'.format(**data), ms)
            statsd.timing('{pre}.{module}.{method}'.format(**data), ms)
            statsd.timing('{pre}.{method}'.format(**data), ms)


class GZipMiddleware(BaseGZipMiddleware):
    """
    Wrapper around GZipMiddleware, which only enables gzip for API responses.
    It specifically avoids enabling it for non-API responses because that might
    leak security tokens through the BREACH attack.

    https://www.djangoproject.com/weblog/2013/aug/06/breach-and-django/
    http://breachattack.com/
    https://bugzilla.mozilla.org/show_bug.cgi?id=960752
    """

    def process_response(self, request, response):
        if not getattr(request, 'API', False):
            return response

        return super(GZipMiddleware, self).process_response(request, response)


class AuthenticationMiddleware(BaseAuthenticationMiddleware):
    """
    Wrapper around AuthenticationMiddleware, which only performs the django
    session based auth for non-API requests.
    """

    def process_request(self, request):
        if getattr(request, 'API', False):
            request.user = AnonymousUser()
        else:
            super(AuthenticationMiddleware, self).process_request(request)


METHOD_OVERRIDE_HEADER = 'HTTP_X_HTTP_METHOD_OVERRIDE'


class MethodOverrideMiddleware(object):
    def process_view(self, request, callback, callback_args, callback_kwargs):
        if request.method != 'POST':
            return
        if METHOD_OVERRIDE_HEADER not in request.META:
            return
        request.method = request.META[METHOD_OVERRIDE_HEADER]
