import datetime
import importlib
import json
import os
from urlparse import urlparse

from django.conf import settings
from django.core.files.storage import default_storage as storage
from django.core.urlresolvers import resolve
from django.http import HttpResponse, Http404
from django.shortcuts import render
from django.views.decorators.cache import cache_control
from django.views.decorators.gzip import gzip_page

import jingo
import jinja2
import newrelic.agent
import waffle
from cache_nuggets.lib import memoize

from mkt.regions.middleware import RegionMiddleware
from mkt.account.helpers import fxa_auth_info
from mkt.webapps.models import Webapp


def get_whitelisted_origins(request, include_loop=True):
    current_domain = settings.DOMAIN
    current_origin = '%s://%s' % ('https' if request.is_secure() else 'http',
                                  current_domain)
    development_server = (settings.DEBUG or
                          current_domain == 'marketplace-dev.allizom.org')

    origin_whitelist = [
        # Start by whitelisting the 2 app:// variants for the current domain,
        # and then whitelist the current http or https origin.
        'app://packaged.%s' % current_domain,
        'app://%s' % current_domain,
        current_origin,
        # Also include Tarako
        'app://tarako.%s' % current_domain,
    ]

    # On dev, also allow localhost/mp.dev.
    if development_server:
        origin_whitelist.extend([
            'http://localhost:8675',
            'https://localhost:8675',
            'http://localhost',
            'https://localhost',
            'http://mp.dev',
            'https://mp.dev',
        ])

    if include_loop:
        # Include loop origins if necessary.
        origin_whitelist.extend([
            'https://hello.firefox.com',
            'https://call.firefox.com',
        ])
        # On dev, include loop dev origin as well.
        if development_server:
            origin_whitelist.extend([
                'http://loop-webapp.dev.mozaws.net',
            ])

    return json.dumps(origin_whitelist)


def get_build_id(repo):
    try:
        # This is where the `build_{repo}.py` files get written to after
        # compiling and minifying our assets.
        # Get the `BUILD_ID` from `build_{repo}.py` and use that to
        # cache-bust the assets for this repo's CSS/JS minified bundles.
        module = 'build_%s' % repo
        return importlib.import_module(module).BUILD_ID
    except (ImportError, AttributeError):
        try:
            build_id_fn = os.path.join(settings.MEDIA_ROOT, repo,
                                       'build_id.txt')
            with storage.open(build_id_fn) as fh:
                return fh.read()
        except:
            # Either `build_{repo}.py` does not exist or `build_{repo}.py`
            # exists but does not contain `BUILD_ID`. Fall back to
            # `BUILD_ID_JS` which is written to `build.py` by jingo-minify.
            try:
                from build import BUILD_ID_CSS
                return BUILD_ID_CSS
            except ImportError:
                return 'dev'


def get_imgurls(repo):
    imgurls_fn = os.path.join(settings.MEDIA_ROOT, repo, 'imgurls.txt')
    with storage.open(imgurls_fn) as fh:
        return list(set(fh.readlines()))


@gzip_page
@cache_control(max_age=settings.CACHE_MIDDLEWARE_SECONDS)
def commonplace(request, repo, **kwargs):
    if repo not in settings.COMMONPLACE_REPOS:
        raise Http404

    BUILD_ID = get_build_id(repo)

    ua = request.META.get('HTTP_USER_AGENT', '').lower()

    include_splash = False
    detect_region_with_geoip = False
    if repo == 'fireplace':
        include_splash = True
        has_sim_info_in_query = ('mccs' in request.GET or
            ('mcc' in request.GET and 'mnc' in request.GET))
        if not has_sim_info_in_query:
            # If we didn't receive mcc/mnc, then use geoip to detect region,
            # enabling fireplace to avoid the consumer_info API call that it
            # does normally to fetch the region.
            detect_region_with_geoip = True
    elif repo == 'discoplace':
        include_splash = True

    # We never want to include persona shim if firefox accounts is enabled:
    # native fxa already provides navigator.id, and fallback fxa doesn't
    # need it.
    fxa_auth_state, fxa_auth_url = fxa_auth_info()
    site_settings = {
        'fxa_auth_state': fxa_auth_state,
        'fxa_auth_url': fxa_auth_url
    }

    site_settings['fxa_css_path'] = settings.FXA_CSS_PATH

    ctx = {
        'BUILD_ID': BUILD_ID,
        'appcache': repo in settings.COMMONPLACE_REPOS_APPCACHED,
        'include_persona': False,
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

    return render(request, 'commonplace/index.html', ctx)


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
def appcache_manifest(request):
    """Serves the appcache manifest."""
    repo = request.GET.get('repo')
    if not repo or repo not in settings.COMMONPLACE_REPOS_APPCACHED:
        raise Http404
    template = _appcache_manifest_template(repo)
    return HttpResponse(template, content_type='text/cache-manifest')


@memoize('appcache-manifest-template')
def _appcache_manifest_template(repo):
    ctx = {
        'BUILD_ID': get_build_id(repo),
        'imgurls': get_imgurls(repo),
        'repo': repo,
        'timestamp': datetime.datetime.now(),
    }
    t = jingo.env.get_template('commonplace/manifest.appcache').render(ctx)
    return unicode(jinja2.Markup(t))


@gzip_page
def iframe_install(request):
    return render(request, 'commonplace/iframe-install.html', {
        'whitelisted_origins': get_whitelisted_origins(request)
    })


@gzip_page
def potatolytics(request):
    return render(request, 'commonplace/potatolytics.html', {
        'whitelisted_origins': get_whitelisted_origins(request,
                                                       include_loop=False)
    })
