import json
import os
from urlparse import urlparse

from django.conf import settings
from django.core.urlresolvers import resolve
from django.http import Http404
from django.shortcuts import render
from django.utils import translation
from django.views.decorators.cache import cache_control
from django.views.decorators.gzip import gzip_page

import newrelic.agent
import waffle

from mkt.account.helpers import fxa_auth_info
from mkt.commonplace.models import DeployBuildId
from mkt.regions.middleware import RegionMiddleware
from mkt.site.storage_utils import local_storage
from mkt.webapps.models import Webapp


@gzip_page
@cache_control(max_age=settings.CACHE_MIDDLEWARE_SECONDS)
def commonplace(request, repo, **kwargs):
    """Serves the frontend single-page apps."""
    if repo not in settings.FRONTEND_REPOS:
        raise Http404

    BUILD_ID = get_build_id(repo)

    ua = request.META.get('HTTP_USER_AGENT', '').lower()

    include_splash = False
    detect_region_with_geoip = False
    if repo == 'fireplace':
        include_splash = True
        has_sim_info_in_query = (
            'mccs' in request.GET or
            ('mcc' in request.GET and 'mnc' in request.GET))
        if not has_sim_info_in_query:
            # If we didn't receive mcc/mnc, then use geoip to detect region,
            # enabling fireplace to avoid the consumer_info API call that it
            # does normally to fetch the region.
            detect_region_with_geoip = True

    fxa_auth_state, fxa_auth_url = fxa_auth_info()
    site_settings = {
        'dev_pay_providers': settings.DEV_PAY_PROVIDERS,
        'fxa_auth_state': fxa_auth_state,
        'fxa_auth_url': fxa_auth_url,
    }

    ctx = {
        'BUILD_ID': BUILD_ID,
        'LANG': request.LANG,
        'DIR': lang_dir(request.LANG),
        'include_splash': include_splash,
        'repo': repo,
        'robots': 'googlebot' in ua,
        'site_settings': site_settings,
        'newrelic_header': newrelic.agent.get_browser_timing_header,
        'newrelic_footer': newrelic.agent.get_browser_timing_footer,
    }

    if repo == 'fireplace':
        # For OpenGraph stuff.
        resolved_url = resolve(request.path)
        if resolved_url.url_name == 'detail':
            ctx = add_app_ctx(ctx, resolved_url.kwargs['app_slug'])

    ctx['waffle_switches'] = list(
        waffle.models.Switch.objects.filter(active=True)
                                    .values_list('name', flat=True))

    media_url = urlparse(settings.MEDIA_URL)
    if media_url.netloc:
        ctx['media_origin'] = media_url.scheme + '://' + media_url.netloc

    if detect_region_with_geoip:
        region_middleware = RegionMiddleware()
        ctx['geoip_region'] = region_middleware.region_from_request(request)

    if repo in settings.REACT_REPOS:
        return render(request, 'commonplace/index_react.html', ctx)
    elif repo in settings.COMMONPLACE_REPOS:
        return render(request, 'commonplace/index.html', ctx)


def get_allowed_origins(request, include_loop=True):
    current_domain = settings.DOMAIN
    current_origin = '%s://%s' % ('https' if request.is_secure() else 'http',
                                  current_domain)
    development_server = (settings.DEBUG or
                          current_domain == 'marketplace-dev.allizom.org')

    allowed = [
        # Start by allowing the 2 app:// variants for the current domain,
        # and then add the current http or https origin.
        'app://packaged.%s' % current_domain,
        'app://%s' % current_domain,
        current_origin,
        # Also include Tarako
        'app://tarako.%s' % current_domain,
    ]

    # On dev, also allow localhost/mp.dev.
    if development_server:
        allowed.extend([
            'http://localhost:8675',
            'https://localhost:8675',
            'http://localhost',
            'https://localhost',
            'http://mp.dev',
            'https://mp.dev',
        ])

    if include_loop:
        # Include loop origins if necessary.
        allowed.extend([
            'https://hello.firefox.com',
            'https://call.firefox.com',
        ])
        # On dev, include loop dev & stage origin as well.
        if development_server:
            allowed.extend([
                'https://loop-webapp-dev.stage.mozaws.net',
                'https://call.stage.mozaws.net',
            ])

    return json.dumps(allowed)


def get_build_id(repo):
    try:
        # Get the build ID from the database (bug 1083185).
        return DeployBuildId.objects.get(repo=repo).build_id
    except DeployBuildId.DoesNotExist:
        # If we haven't initialized a build ID yet, read it directly from the
        # build_id.txt by our frontend builds.
        try:
            build_id_path = os.path.join(settings.MEDIA_ROOT, repo,
                                         'build_id.txt')
            with local_storage.open(build_id_path) as f:
                return f.read()
        except:
            return 'dev'


def fxa_authorize(request):
    """
    A page to mimic commonplace's fxa-authorize page to handle login.
    """
    return render(request, 'commonplace/fxa_authorize.html')


def add_app_ctx(ctx, app_slug):
    """
    If we are hitting the Fireplace detail page, get the app for Open Graph
    tags.
    """
    try:
        app = Webapp.objects.get(app_slug=app_slug)
        ctx['app'] = app
    except Webapp.DoesNotExist:
        pass
    return ctx


@gzip_page
def iframe_install(request):
    return render(request, 'commonplace/iframe-install.html', {
        'allowed_origins': get_allowed_origins(request)
    })


@gzip_page
def potatolytics(request):
    return render(request, 'commonplace/potatolytics.html', {
        'allowed_origins': get_allowed_origins(request,
                                               include_loop=False)
    })


def lang_dir(lang):
    if lang == 'rtl' or translation.get_language_bidi():
        return 'rtl'
    else:
        return 'ltr'
