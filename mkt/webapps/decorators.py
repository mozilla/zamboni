import functools

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

import commonware.log

from mkt.webapps.models import Webapp


log = commonware.log.getLogger('mkt.purchase')


def has_purchased(f):
    """
    If the webapp is premium, require a purchase.
    Must be called after webapp_view decorator.
    """
    @functools.wraps(f)
    def wrapper(request, webapp, *args, **kw):
        if webapp.is_premium() and not webapp.has_purchased(request.user):
            log.info('Not purchased: %d' % webapp.pk)
            raise PermissionDenied
        return f(request, webapp, *args, **kw)
    return wrapper


def can_become_premium(f):
    """Check that the webapp can become premium."""
    @functools.wraps(f)
    def wrapper(request, webapp_id, webapp, *args, **kw):
        if not webapp.can_become_premium():
            log.info('Cannot become premium: %d' % webapp.pk)
            raise PermissionDenied
        return f(request, webapp_id, webapp, *args, **kw)
    return wrapper


def app_view(f, qs=Webapp.objects.all):
    @functools.wraps(f)
    def wrapper(request, app_slug, *args, **kw):
        webapp = get_object_or_404(qs(), app_slug=app_slug)
        return f(request, webapp, *args, **kw)
    return wrapper


def app_view_factory(qs):
    """
    Don't evaluate qs or the locale will get stuck on whatever the server
    starts with. The app_view() decorator will call qs with no arguments before
    doing anything, so lambdas are ok.

        GOOD: Webapp.objects.valid
        GOOD: lambda: Webapp.objects.valid().filter(...)
        BAD: Webapp.objects.valid()

    """
    return functools.partial(app_view, qs=qs)
