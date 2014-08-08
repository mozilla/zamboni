import datetime
import importlib
import os
from urlparse import urlparse

from django.conf import settings
from django.core.files.storage import default_storage as storage
from django.http import HttpResponse, Http404
from django.shortcuts import render

import jingo
import jinja2
import newrelic.agent
import waffle

from cache_nuggets.lib import memoize


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
            build_id_fn = os.path.join(settings.MEDIA_ROOT, repo, 'build_id.txt')
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

    media_url = urlparse(settings.MEDIA_URL)
    if media_url.netloc:
        ctx['media_origin'] = media_url.scheme + '://' + media_url.netloc

    return render(request, 'commonplace/index.html', ctx)


def appcache_manifest(request):
    """Serves the appcache manifest."""
    repo = request.GET.get('repo')
    if not repo or repo not in settings.COMMONPLACE_REPOS_APPCACHED:
        raise Http404
    template = appcache_manifest_template(repo)
    return HttpResponse(template, content_type='text/cache-manifest')


@memoize('appcache-manifest-template')
def appcache_manifest_template(repo):
    ctx = {
        'BUILD_ID': get_build_id(repo),
        'imgurls': get_imgurls(repo),
        'repo': repo,
        'timestamp': datetime.datetime.now(),
    }
    t = jingo.env.get_template('commonplace/manifest.appcache').render(ctx)
    return unicode(jinja2.Markup(t))


def iframe_install(request):
    return render(request, 'commonplace/iframe-install.html')
