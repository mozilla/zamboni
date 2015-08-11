import functools

from django.core.exceptions import PermissionDenied

import commonware.log

log = commonware.log.getLogger('mkt.purchase')


def can_become_premium(f):
    """Check that the webapp can become premium."""
    @functools.wraps(f)
    def wrapper(request, webapp_id, webapp, *args, **kw):
        if not webapp.can_become_premium():
            log.info('Cannot become premium: %d' % webapp.pk)
            raise PermissionDenied
        return f(request, webapp_id, webapp, *args, **kw)
    return wrapper


def can_be_purchased(f):
    """
    Check if it can be purchased, returns False if not premium.
    Must be called after the app_view decorator.
    """
    @functools.wraps(f)
    def wrapper(request, webapp, *args, **kw):
        if not webapp.can_be_purchased():
            log.info('Cannot be purchased: %d' % webapp.pk)
            raise PermissionDenied
        return f(request, webapp, *args, **kw)
    return wrapper


def has_purchased(f):
    """
    If the webapp is premium, require a purchase.
    Must be called after app_view decorator.
    """
    @functools.wraps(f)
    def wrapper(request, webapp, *args, **kw):
        if webapp.is_premium() and not webapp.has_purchased(request.user):
            log.info('Not purchased: %d' % webapp.pk)
            raise PermissionDenied
        return f(request, webapp, *args, **kw)
    return wrapper
