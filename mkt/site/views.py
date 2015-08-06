import hashlib
import json
import os
import subprocess

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import (HttpResponse, HttpResponseBadRequest,
                         HttpResponseNotFound, HttpResponseServerError)
from django.shortcuts import render
from django.template import RequestContext
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt, requires_csrf_token
from django.views.decorators.http import etag, require_POST
from django.views.generic.base import TemplateView

import commonware.log
import jingo_minify
import waffle
from jingo.helpers import urlparams
from django_statsd.clients import statsd
from django_statsd.views import record as django_statsd_record

from mkt.carriers import get_carrier
from mkt.detail.views import manifest as mini_manifest
from mkt.site import monitors
from mkt.site.context_processors import get_collect_timings
from mkt.site.helpers import media
from mkt.site.utils import log_cef


log = commonware.log.getLogger('z.mkt.site')


# This can be called when CsrfViewMiddleware.process_view has not run,
# therefore needs @requires_csrf_token in case the template needs
# {% csrf_token %}.
@requires_csrf_token
def handler403(request):
    # TODO: Bug 793241 for different 403 templates at different URL paths.
    return render(request, 'site/403.html', status=403)


def handler404(request):
    if request.path_info.startswith('/api/'):
        # Pass over to API handler404 view if API was targeted.
        return HttpResponseNotFound()
    else:
        return render(request, 'site/404.html', status=404)


def handler500(request):
    if request.path_info.startswith('/api/'):
        # Pass over to API handler500 view if API was targeted.
        return HttpResponseServerError()
    else:
        return render(request, 'site/500.html', status=500)


def csrf_failure(request, reason=''):
    return render(request, 'site/403.html',
                  {'because_csrf': 'CSRF' in reason}, status=403)


def manifest(request):
    ctx = RequestContext(request)
    data = {
        'name': getattr(settings, 'WEBAPP_MANIFEST_NAME',
                        'Firefox Marketplace'),
        'description': 'The Firefox Marketplace',
        'developer': {
            'name': 'Mozilla',
            'url': 'http://mozilla.org',
        },
        'icons': {
            # Using the default addon image until we get a marketplace logo.
            '128': media(ctx, 'img/mkt/logos/128.png'),
            '64': media(ctx, 'img/mkt/logos/64.png'),
            '32': media(ctx, 'img/mkt/logos/32.png'),
        },
        'activities': {
            'marketplace-app': {'href': '/'},
            'marketplace-app-rating': {'href': '/'},
            'marketplace-category': {'href': '/'},
            'marketplace-search': {'href': '/'},
        }
    }
    if get_carrier():
        data['launch_path'] = urlparams('/', carrier=get_carrier())

    manifest_content = json.dumps(data)
    manifest_etag = hashlib.sha256(manifest_content).hexdigest()

    @etag(lambda r: manifest_etag)
    def _inner_view(request):
        response = HttpResponse(
            manifest_content,
            content_type='application/x-web-app-manifest+json')
        return response

    return _inner_view(request)


def serve_contribute(request):
    filename = os.path.join(settings.ROOT, 'contribute.json')
    with open(filename) as fd:
        content = fd.read()
    return HttpResponse(content, content_type='application/json')


def package_minifest(request):
    """Serve mini manifest ("minifest") for Yulelog's packaged `.zip`."""
    if not settings.MARKETPLACE_GUID:
        return HttpResponseNotFound()
    return mini_manifest(request, settings.MARKETPLACE_GUID)


def yogafire_minifest(request):
    """Serve mini manifest ("minifest") for Yogafire's packaged `.zip`."""
    if not settings.YOGAFIRE_GUID:
        return HttpResponseNotFound()
    return mini_manifest(request, settings.YOGAFIRE_GUID)


def robots(request):
    """Generate a `robots.txt`."""
    template = render(request, 'site/robots.txt')
    return HttpResponse(template, content_type='text/plain')


@csrf_exempt
@require_POST
def record(request):
    # The rate limiting is done up on the client, but if things go wrong
    # we can just turn the percentage down to zero.
    if get_collect_timings():
        return django_statsd_record(request)
    raise PermissionDenied


@statsd.timer('mkt.mozmarket.minify')
def minify_js(js):
    if settings.UGLIFY_BIN:
        log.info('minifying JS with uglify')
        return _minify_js_with_uglify(js)
    else:
        # The YUI fallback here is important
        # because YUI compressor is bundled with jingo
        # minify and therefore doesn't require any deps.
        log.info('minifying JS with YUI')
        return _minify_js_with_yui(js)


def _minify_js_with_uglify(js):
    sp = _open_pipe([settings.UGLIFY_BIN])
    js, err = sp.communicate(js)
    if sp.returncode != 0:
        raise ValueError('Compressing JS with uglify failed; error: %s'
                         % err.strip())
    return js


def _minify_js_with_yui(js):
    jar = os.path.join(os.path.dirname(jingo_minify.__file__), 'bin',
                       'yuicompressor-2.4.7.jar')
    if not os.path.exists(jar):
        raise ValueError('Could not find YUI compressor; tried %r' % jar)
    sp = _open_pipe([settings.JAVA_BIN, '-jar', jar, '--type', 'js',
                     '--charset', 'utf8'])
    js, err = sp.communicate(js)
    if sp.returncode != 0:
        raise ValueError('Compressing JS with YUI failed; error: %s'
                         % err.strip())
    return js


def _open_pipe(cmd):
    return subprocess.Popen(cmd,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)


class OpensearchView(TemplateView):
    content_type = 'text/xml'
    template_name = 'mkt/opensearch.xml'


@never_cache
def monitor(request, format=None):

    # For each check, a boolean pass/fail status to show in the template
    status_summary = {}
    results = {}

    checks = ['memcache', 'libraries', 'elastic', 'package_signer', 'path',
              'receipt_signer', 'settings_check', 'solitude']

    for check in checks:
        with statsd.timer('monitor.%s' % check) as timer:
            status, result = getattr(monitors, check)()
        # state is a string. If it is empty, that means everything is fine.
        status_summary[check] = {'state': not status,
                                 'status': status}
        results['%s_results' % check] = result
        results['%s_timer' % check] = timer.ms

    # If anything broke, send HTTP 500.
    status_code = 200 if all(a['state']
                             for a in status_summary.values()) else 500

    if format == '.json':
        return HttpResponse(json.dumps(status_summary), status=status_code)
    ctx = {}
    ctx.update(results)
    ctx['status_summary'] = status_summary

    return render(request, 'services/monitor.html', ctx, status=status_code)


def loaded(request):
    return HttpResponse('%s' % request.META['wsgi.loaded'],
                        content_type='text/plain')


@csrf_exempt
@require_POST
def cspreport(request):
    """Accept CSP reports and log them."""
    report = ('blocked-uri', 'violated-directive', 'original-policy')

    if not waffle.sample_is_active('csp-store-reports'):
        return HttpResponse()

    try:
        v = json.loads(request.body)['csp-report']
        # If possible, alter the PATH_INFO to contain the request of the page
        # the error occurred on, spec: http://mzl.la/P82R5y
        meta = request.META.copy()
        meta['PATH_INFO'] = v.get('document-uri', meta['PATH_INFO'])
        v = [(k, v[k]) for k in report if k in v]
        log_cef('CSPViolation', 5, meta,
                signature='CSPREPORT',
                msg='A client reported a CSP violation',
                cs6=v, cs6Label='ContentPolicy')
    except (KeyError, ValueError), e:
        log.debug('Exception in CSP report: %s' % e, exc_info=True)
        return HttpResponseBadRequest()

    return HttpResponse()
