import functools

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

import commonware.log

from mkt.webapps.models import Webapp


log = commonware.log.getLogger('mkt.purchase')


def has_purchased(f):
    """
    If the addon is premium, require a purchase.
    Must be called after addon_view decorator.
    """
    @functools.wraps(f)
    def wrapper(request, addon, *args, **kw):
        if addon.is_premium() and not addon.has_purchased(request.user):
            log.info('Not purchased: %d' % addon.pk)
            raise PermissionDenied
        return f(request, addon, *args, **kw)
    return wrapper


def can_become_premium(f):
    """Check that the addon can become premium."""
    @functools.wraps(f)
    def wrapper(request, addon_id, addon, *args, **kw):
        if not addon.can_become_premium():
            log.info('Cannot become premium: %d' % addon.pk)
            raise PermissionDenied
        return f(request, addon_id, addon, *args, **kw)
    return wrapper


def app_view(f, qs=Webapp.objects.all):
    @functools.wraps(f)
    def wrapper(request, app_slug, *args, **kw):
        addon = get_object_or_404(qs(), app_slug=app_slug)
        return f(request, addon, *args, **kw)
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
