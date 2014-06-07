import functools

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.views.decorators.cache import never_cache

import amo
from amo.decorators import json_view, login_required
from mkt.access import acl
from mkt.reviewers.utils import AppsReviewing
from users.models import UserProfile


def _view_on_get(request):
    """Returns whether the user can access this page.

    If the user is in a group with rule 'ReviewerTools:View' and the request is
    a GET request, they are allowed to view.
    """
    return (request.method == 'GET' and
            acl.action_allowed(request, 'ReviewerTools', 'View'))


def reviewer_required(region=None):
    """Requires the user to be logged in as a reviewer or admin, or allows
    someone with rule 'ReviewerTools:View' for GET requests.

    Reviewer is someone who is in one of the groups with the following
    permissions:

        Addons:Review
        Apps:Review
        Personas:Review

    """
    def decorator(f):
        @login_required
        @functools.wraps(f)
        def wrapper(request, *args, **kw):
            if (acl.check_reviewer(request, region=kw.get('region')) or
                _view_on_get(request)):
                return f(request, *args, **kw)
            else:
                raise PermissionDenied
        return wrapper
    # If decorator has no args, and is "paren-less", it's callable.
    if callable(region):
        return decorator(region)
    else:
        return decorator


@never_cache
@json_view
@reviewer_required
def review_viewing(request):
    if 'addon_id' not in request.POST:
        return {}

    addon_id = request.POST['addon_id']
    user_id = request.amo_user.id
    current_name = ''
    is_user = 0
    key = '%s:review_viewing:%s' % (settings.CACHE_PREFIX, addon_id)
    interval = amo.EDITOR_VIEWING_INTERVAL

    # Check who is viewing.
    currently_viewing = cache.get(key)

    # If nobody is viewing or current user is, set current user as viewing
    if not currently_viewing or currently_viewing == user_id:
        # We want to save it for twice as long as the ping interval,
        # just to account for latency and the like.
        cache.set(key, user_id, interval * 2)
        currently_viewing = user_id
        current_name = request.amo_user.name
        is_user = 1
    else:
        current_name = UserProfile.objects.get(pk=currently_viewing).name

    AppsReviewing(request).add(addon_id)

    return {'current': currently_viewing, 'current_name': current_name,
            'is_user': is_user, 'interval_seconds': interval}


@never_cache
@json_view
@reviewer_required
def queue_viewing(request):
    if 'addon_ids' not in request.POST:
        return {}

    viewing = {}
    user_id = request.amo_user.id

    for addon_id in request.POST['addon_ids'].split(','):
        addon_id = addon_id.strip()
        key = '%s:review_viewing:%s' % (settings.CACHE_PREFIX, addon_id)
        currently_viewing = cache.get(key)
        if currently_viewing and currently_viewing != user_id:
            viewing[addon_id] = (UserProfile.objects
                                            .get(id=currently_viewing)
                                            .display_name)

    return viewing
