import contextlib

from django import http
from django.db import models

from . import urlresolvers


@contextlib.contextmanager
def hera_disabled():
    _disconnect()
    try:
        yield
    finally:
        _connect()


## Hook up test signals here, for lack of a better spot.

def clean_url_prefixes(sender, **kwargs):
    """Wipe the URL prefixer(s) after each test."""
    urlresolvers.clean_url_prefixes()


def default_prefixer(sender, **kwargs):
    """Make sure each test starts with a default URL prefixer."""
    request = http.HttpRequest()
    request.META['SCRIPT_NAME'] = ''
    prefixer = urlresolvers.Prefixer(request)
    urlresolvers.set_url_prefix(prefixer)


# Register Django signals this app listens to.
try:
    import test_utils.signals
except ImportError:
    pass
else:
    # Clean up URL prefix cache when a new test is invoked.
    test_utils.signals.pre_setup.connect(default_prefixer)
    test_utils.signals.post_teardown.connect(clean_url_prefixes)
