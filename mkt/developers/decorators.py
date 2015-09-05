import functools

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied

from mkt.access import acl
from mkt.site.decorators import login_required
from mkt.webapps.decorators import app_view


def dev_required(owner_for_post=False, allow_editors=False, support=False,
                 webapp=False, skip_submit_check=False, staff=False):
    """Requires user to be add-on owner or admin.

    When allow_editors is True, an editor can view the page.

    When `staff` is True, users in the Staff or Support Staff groups are
    allowed. Users in the Developers group are allowed read-only.
    """
    def decorator(f):
        @app_view
        @login_required
        @functools.wraps(f)
        def wrapper(request, webapp, *args, **kw):
            from mkt.submit.views import _resume

            def fun():
                return f(request, webapp_id=webapp.id, webapp=webapp,
                         *args, **kw)

            if allow_editors and acl.check_reviewer(request):
                return fun()

            if staff and (acl.action_allowed(request, 'Apps', 'Configure') or
                          acl.action_allowed(request, 'Apps',
                                             'ViewConfiguration')):
                return fun()

            if support:
                # Let developers and support people do their thangs.
                if (acl.check_webapp_ownership(request, webapp,
                                               support=True) or
                    acl.check_webapp_ownership(request, webapp,
                                               dev=True)):
                    return fun()
            else:
                # Require an owner or dev for POST requests.
                if request.method == 'POST':

                    if acl.check_webapp_ownership(request, webapp,
                                                  dev=not owner_for_post):
                        return fun()

                # Ignore disabled so they can view their add-on.
                elif acl.check_webapp_ownership(request, webapp, viewer=True,
                                                ignore_disabled=True):
                    if not skip_submit_check:
                        try:
                            # If it didn't go through the app submission
                            # checklist. Don't die. This will be useful for
                            # creating apps with an API later.
                            step = webapp.appsubmissionchecklist.get_next()
                        except ObjectDoesNotExist:
                            step = None
                        # Redirect to the submit flow if they're not done.
                        if not getattr(f, 'submitting', False) and step:
                            return _resume(webapp, step)
                    return fun()

            raise PermissionDenied
        return wrapper
    # The arg will be a function if they didn't pass owner_for_post.
    if callable(owner_for_post):
        f = owner_for_post
        owner_for_post = False
        return decorator(f)
    else:
        return decorator
