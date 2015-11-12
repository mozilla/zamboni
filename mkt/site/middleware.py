import contextlib
from types import MethodType

from django.conf import settings
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.urlresolvers import is_valid_path
from django.http import (HttpRequest, HttpResponsePermanentRedirect,
                         SimpleCookie)
from django.middleware import common
from django.utils.cache import (get_max_age, patch_cache_control,
                                patch_response_headers, patch_vary_headers)
from django.utils.encoding import iri_to_uri
from django.utils.translation.trans_real import parse_accept_lang_header

import tower


def _set_cookie(self, key, value='', max_age=None, expires=None, path='/',
                domain=None, secure=False):
    self._resp_cookies[key] = value
    self.COOKIES[key] = value
    if max_age is not None:
        self._resp_cookies[key]['max-age'] = max_age
    if expires is not None:
        self._resp_cookies[key]['expires'] = expires
    if path is not None:
        self._resp_cookies[key]['path'] = path
    if domain is not None:
        self._resp_cookies[key]['domain'] = domain
    if secure:
        self._resp_cookies[key]['secure'] = True


def _delete_cookie(self, key, path='/', domain=None):
    self.set_cookie(key, max_age=0, path=path, domain=domain,
                    expires='Thu, 01-Jan-1970 00:00:00 GMT')
    try:
        del self.COOKIES[key]
    except KeyError:
        pass


class RequestCookiesMiddleware(object):
    """
    Allows setting and deleting of cookies from requests in exactly the same
    way as we do for responses.

        >>> request.set_cookie('name', 'value')

    The `set_cookie` and `delete_cookie` are exactly the same as the ones
    built into Django's `HttpResponse` class.

    I had a half-baked cookie middleware (pun intended), but then I stole this
    from Paul McLanahan: http://paulm.us/post/1660050353/cookies-for-django
    """

    def process_request(self, request):
        request._resp_cookies = SimpleCookie()
        request.set_cookie = MethodType(_set_cookie, request, HttpRequest)
        request.delete_cookie = MethodType(_delete_cookie, request,
                                           HttpRequest)

    def process_response(self, request, response):
        if getattr(request, '_resp_cookies', None):
            response.cookies.update(request._resp_cookies)
        return response


def lang_from_accept_header(header):
    # Map all our lang codes and any prefixes to the locale code.
    langs = dict((k.lower(), v) for k, v in settings.LANGUAGE_URL_MAP.items())

    # If we have a lang or a prefix of the lang, return the locale code.
    for lang, _ in parse_accept_lang_header(header.lower()):
        if lang in langs:
            return langs[lang]

        prefix = lang.split('-')[0]
        # Downgrade a longer prefix to a shorter one if needed (es-PE > es)
        if prefix in langs:
            return langs[prefix]
        # Upgrade to a longer one, if present (zh > zh-CN)
        lookup = settings.SHORTER_LANGUAGES.get(prefix, '').lower()
        if lookup and lookup in langs:
            return langs[lookup]

    return settings.LANGUAGE_CODE


class LocaleMiddleware(object):
    """Figure out the user's locale and store it in a cookie."""

    def process_request(self, request):
        a_l = lang_from_accept_header(request.META.get('HTTP_ACCEPT_LANGUAGE',
                                                       ''))
        lang, ov_lang = a_l, ''
        stored_lang, stored_ov_lang = '', ''

        remembered = request.COOKIES.get('lang')
        if remembered:
            chunks = remembered.split(',')[:2]

            stored_lang = chunks[0]
            try:
                stored_ov_lang = chunks[1]
            except IndexError:
                pass

            if stored_lang.lower() in settings.LANGUAGE_URL_MAP:
                lang = stored_lang
            if stored_ov_lang.lower() in settings.LANGUAGE_URL_MAP:
                ov_lang = stored_ov_lang

        if 'lang' in request.GET:
            # `get_language` uses request.GET['lang'] and does safety checks.
            ov_lang = a_l
            lang = self.get_language(request)
        elif a_l != ov_lang:
            # Change if Accept-Language differs from Overridden Language.
            lang = a_l
            ov_lang = ''

        # Update cookie if values have changed.
        if lang != stored_lang or ov_lang != stored_ov_lang:
            request.LANG_COOKIE = ','.join([lang, ov_lang])
        if request.user.is_authenticated() and request.user.lang != lang:
            request.user.lang = lang
            request.user.save()
        request.LANG = lang
        tower.activate(lang)

    def process_response(self, request, response):
        # We want to change the cookie, but didn't have the response in
        # process request.
        if (hasattr(request, 'LANG_COOKIE') and
                not getattr(request, 'API', False)):
            response.set_cookie('lang', request.LANG_COOKIE)

        if request.GET.get('vary') == '0':
            del response['Vary']
        else:
            patch_vary_headers(response, ['Accept-Language', 'Cookie'])

        return response

    def get_language(self, request):
        """
        Return a locale code that we support on the site using the
        user's Accept Language header to determine which is best.  This
        mostly follows the RFCs but read bug 439568 for details.
        """
        data = (request.GET or request.POST)
        if 'lang' in data:
            lang = data['lang'].lower()
            if lang in settings.LANGUAGE_URL_MAP:
                return settings.LANGUAGE_URL_MAP[lang]
            prefix = lang.split('-')[0]
            if prefix in settings.LANGUAGE_URL_MAP:
                return settings.LANGUAGE_URL_MAP[prefix]

        accept = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
        return lang_from_accept_header(accept)


class DeviceDetectionMiddleware(object):
    """If the user has flagged that they are on a device. Store the device."""
    devices = ['mobile', 'gaia', 'tablet']

    def process_request(self, request):
        dev = request.GET.get('dev')
        if dev:
            request.MOBILE = dev == 'android'
            request.GAIA = dev in ['firefoxos', 'firefoxos+mobile']
            request.TV = dev == 'firefoxos+tv'
            request.TABLET = dev == 'desktop'
            return

        # TODO: These are deprecated, remove them. Update the docs (and API
        # docs).
        for device in self.devices:
            qs = request.GET.get(device, False)
            cookie = request.COOKIES.get(device, False)
            # If the qs is True or there's a cookie set the device. But not if
            # the qs is False.
            if qs == 'true' or (cookie and not qs == 'false'):
                setattr(request, device.upper(), True)
                continue

            # Otherwise set to False.
            setattr(request, device.upper(), False)

    def process_response(self, request, response):
        for device in self.devices:
            active = getattr(request, device.upper(), False)
            cookie = request.COOKIES.get(device, False)

            if not active and cookie:
                # If the device isn't active, but there is a cookie, remove it.
                response.delete_cookie(device)
            elif active and not cookie and not getattr(request, 'API', False):
                # Set the device if it's active and there's no cookie.
                response.set_cookie(device, 'true')

        return response


class CacheHeadersMiddleware(object):
    """
    Unlike the `django.middleware.cache` middlewares, this middleware
    simply sets the `Cache-Control`, `ETag`, `Expires`, and `Last-Modified`
    headers and doesn't do any caching of the response object.

    """
    allowed_methods = ('GET', 'HEAD', 'OPTIONS')
    allowed_statuses = (200,)

    def process_response(self, request, response):
        if (request.method in self.allowed_methods and
                response.status_code in self.allowed_statuses and
                request.GET.get('cache', '').isdigit()):
            # If there's already a `Cache-Control` header with a `max-age`,
            # use that TTL before falling back to what the client requested.
            timeout = get_max_age(response)
            if timeout is None:
                timeout = int(request.GET['cache'])
                # Never allow clients to choose positive timeouts below
                # settings.CACHE_MIDDLEWARE_SECONDS.
                if timeout > 0 and timeout < settings.CACHE_MIDDLEWARE_SECONDS:
                    timeout = settings.CACHE_MIDDLEWARE_SECONDS
            # Send caching headers, but only timeout is not 0.
            if timeout != 0:
                patch_response_headers(response, timeout)
                patch_cache_control(response, must_revalidate=True)

        return response


class NoVarySessionMiddleware(SessionMiddleware):
    """
    SessionMiddleware sets Vary: Cookie anytime request.session is accessed.
    request.session is accessed indirectly anytime request.user is touched.
    We always touch request.user to see if the user is authenticated, so every
    request would be sending vary, so we'd get no caching.

    We skip the cache in Zeus if someone has an AMOv3 cookie, so varying on
    Cookie at this level only hurts us.
    """

    def process_request(self, request):
        if not getattr(request, 'API', False):
            super(NoVarySessionMiddleware, self).process_request(request)

    def process_response(self, request, response):
        if settings.READ_ONLY:
            return response
        # Let SessionMiddleware do its processing but prevent it from changing
        # the Vary header.
        vary = None
        if hasattr(response, 'get'):
            vary = response.get('Vary', None)
        new_response = (super(NoVarySessionMiddleware, self)
                        .process_response(request, response))
        if vary:
            new_response['Vary'] = vary
        else:
            del new_response['Vary']
        return new_response


class RemoveSlashMiddleware(object):
    """
    Middleware that tries to remove a trailing slash if there was a 404.

    If the response is a 404 because url resolution failed, we'll look for a
    better url without a trailing slash.
    """

    def process_response(self, request, response):
        if (response.status_code == 404 and
                request.path_info.endswith('/') and
                not is_valid_path(request.path_info) and
                is_valid_path(request.path_info[:-1])):
            # Use request.path because we munged app/locale in path_info.
            newurl = request.path[:-1]
            if request.GET:
                with safe_query_string(request):
                    newurl += '?' + request.META.get('QUERY_STRING', '')
            return HttpResponsePermanentRedirect(newurl)
        else:
            return response


@contextlib.contextmanager
def safe_query_string(request):
    """
    Turn the QUERY_STRING into a unicode- and ascii-safe string.

    We need unicode so it can be combined with a reversed URL, but it has to be
    ascii to go in a Location header.  iri_to_uri seems like a good compromise.
    """
    qs = request.META.get('QUERY_STRING', '')
    try:
        request.META['QUERY_STRING'] = iri_to_uri(qs)
        yield
    finally:
        request.META['QUERY_STRING'] = qs


class CommonMiddleware(common.CommonMiddleware):

    def process_request(self, request):
        with safe_query_string(request):
            return super(CommonMiddleware, self).process_request(request)
