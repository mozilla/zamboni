import json

from django import http
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.utils.encoding import iri_to_uri
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

import commonware.log
import waffle
from django_statsd.views import record as django_statsd_record
from django_statsd.clients import statsd

from amo.decorators import post_required
from amo.utils import log_cef
from mkt.site.context_processors import get_collect_timings
from . import monitors

log = commonware.log.getLogger('z.amo')


@never_cache
def monitor(request, format=None):

    # For each check, a boolean pass/fail status to show in the template
    status_summary = {}
    results = {}

    checks = ['memcache', 'libraries', 'elastic', 'package_signer', 'path',
              'redis', 'receipt_signer', 'settings_check', 'solitude']

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
        return http.HttpResponse(json.dumps(status_summary),
                                 status=status_code)
    ctx = {}
    ctx.update(results)
    ctx['status_summary'] = status_summary

    return render(request, 'services/monitor.html', ctx, status=status_code)


def loaded(request):
    return http.HttpResponse('%s' % request.META['wsgi.loaded'],
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
        log_cef('CSPViolation', 5, meta, username=request.user,
                signature='CSPREPORT',
                msg='A client reported a CSP violation',
                cs6=v, cs6Label='ContentPolicy')
    except (KeyError, ValueError), e:
        log.debug('Exception in CSP report: %s' % e, exc_info=True)
        return HttpResponseBadRequest()

    return HttpResponse()


@csrf_exempt
@post_required
def record(request):
    # The rate limiting is done up on the client, but if things go wrong
    # we can just turn the percentage down to zero.
    if get_collect_timings():
        return django_statsd_record(request)
    raise PermissionDenied
