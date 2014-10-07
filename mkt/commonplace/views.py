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
from django.views.decorators.gzip import gzip_page

import jingo
import jinja2
import newrelic.agent
import waffle
from cache_nuggets.lib import memoize

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
def commonplace(request, repo, **kwargs):
    if repo not in settings.COMMONPLACE_REPOS:
        raise Http404

    BUILD_ID = get_build_id(repo)

    ua = request.META.get('HTTP_USER_AGENT', '').lower()

    include_persona = True
    include_splash = False
    if repo == 'fireplace':
        include_splash = True
        if (request.GET.get('nativepersona') or
            'mccs' in request.GET or
            ('mcc' in request.GET and 'mnc' in request.GET)):
            include_persona = False
    elif repo == 'discoplace':
        include_persona = False
        include_splash = True

    if waffle.switch_is_active('firefox-accounts'):
        # We never want to include persona shim if firefox accounts is enabled:
        # native fxa already provides navigator.id, and fallback fxa doesn't
        # need it.
        include_persona = False
        site_settings = {}
    else:
        site_settings = {
            'persona_unverified_issuer': settings.BROWSERID_DOMAIN,
        }

    site_settings['fxa_css_path'] = settings.FXA_CSS_PATH

    ctx = {
        'BUILD_ID': BUILD_ID,
        'appcache': repo in settings.COMMONPLACE_REPOS_APPCACHED,
        'include_persona': include_persona,
        'include_splash': include_splash,
        'repo': repo,
        'robots': 'googlebot' in ua,
        'site_settings': site_settings,
        'newrelic_header': newrelic.agent.get_browser_timing_header,
        'newrelic_footer': newrelic.agent.get_browser_timing_footer,
    }

    # For OpenGraph stuff.
    resolved_url = resolve(request.path)
    if repo == 'fireplace' and resolved_url.url_name == 'detail':
        ctx = add_app_ctx(ctx, resolved_url.kwargs['app_slug'])

    media_url = urlparse(settings.MEDIA_URL)
    if media_url.netloc:
        ctx['media_origin'] = media_url.scheme + '://' + media_url.netloc

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
