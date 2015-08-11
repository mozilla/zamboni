import functools

from django.shortcuts import redirect


def submit_step(outer_step):
    """Wraps the function with a decorator that bounces to the right step."""
    def decorator(f):
        @functools.wraps(f)
        def wrapper(request, *args, **kw):
            from mkt.submit.views import _resume
            from mkt.submit.models import AppSubmissionChecklist
            webapp = kw.get('webapp', False)
            if webapp:
                try:
                    step = webapp.appsubmissionchecklist.get_next()
                except AppSubmissionChecklist.DoesNotExist:
                    step = None
                if step and step != outer_step:
                    return _resume(webapp, step)
            return f(request, *args, **kw)
        wrapper.submitting = True
        return wrapper
    return decorator


def read_dev_agreement_required(f):
    """
    Decorator that checks if the user has read the dev agreement, redirecting
    if not.
    """
    def decorator(f):
        @functools.wraps(f)
        def wrapper(request, *args, **kw):
            if not request.user.read_dev_agreement:
                return redirect('submit.app')
            return f(request, *args, **kw)
        return wrapper
    return decorator(f)
