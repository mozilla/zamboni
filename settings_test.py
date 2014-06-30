import atexit
import os
import tempfile

from mkt.settings import ROOT


_tmpdirs = set()


def _cleanup():
    try:
        import sys
        import shutil
    except ImportError:
        return
    tmp = None
    try:
        for tmp in _tmpdirs:
            shutil.rmtree(tmp)
    except Exception, exc:
        sys.stderr.write("\n** shutil.rmtree(%r): %s\n" % (tmp, exc))

atexit.register(_cleanup)


def _polite_tmpdir():
    tmp = tempfile.mkdtemp()
    _tmpdirs.add(tmp)
    return tmp

# See settings.py for documentation:
IN_TEST_SUITE = True
NETAPP_STORAGE = _polite_tmpdir()
ADDONS_PATH = _polite_tmpdir()
GUARDED_ADDONS_PATH = _polite_tmpdir()
SIGNED_APPS_PATH = _polite_tmpdir()
SIGNED_APPS_REVIEWER_PATH = _polite_tmpdir()
UPLOADS_PATH = _polite_tmpdir()
MIRROR_STAGE_PATH = _polite_tmpdir()
TMP_PATH = _polite_tmpdir()
COLLECTIONS_ICON_PATH = _polite_tmpdir()
REVIEWER_ATTACHMENTS_PATH = _polite_tmpdir()
DUMPED_APPS_PATH = _polite_tmpdir()

AUTHENTICATION_BACKENDS = (
    'django_browserid.auth.BrowserIDBackend',
)
# We won't actually send an email.
SEND_REAL_EMAIL = True

# Turn off search engine indexing.
USE_ELASTIC = False

# Ensure all validation code runs in tests:
VALIDATE_ADDONS = True

PAYPAL_PERMISSIONS_URL = ''

ENABLE_API_ERROR_SERVICE = False

SITE_URL = 'http://testserver'
BROWSERID_AUDIENCES = [SITE_URL]
STATIC_URL = SITE_URL + '/'
MEDIA_URL = '/media/'

CACHES = {
    'default': {
        'BACKEND': 'caching.backends.locmem.LocMemCache',
    }
}

# COUNT() caching can't be invalidated, it just expires after x seconds. This
# is just too annoying for tests, so disable it.
CACHE_COUNT_TIMEOUT = -1

# Overrides whatever storage you might have put in local settings.
DEFAULT_FILE_STORAGE = 'amo.utils.LocalFileStorage'

VIDEO_LIBRARIES = ['lib.video.dummy']

ALLOW_SELF_REVIEWS = True

# Make sure debug toolbar output is disabled so it doesn't interfere with any
# html tests.


DEBUG_TOOLBAR_CONFIG = {
    'INTERCEPT_REDIRECTS': False,
    'SHOW_TOOLBAR_CALLBACK': lambda r: False,
    'HIDE_DJANGO_SQL': True,
    'TAG': 'div',
    'ENABLE_STACKTRACES': False,
}

MOZMARKET_VENDOR_EXCLUDE = []

TASK_USER_ID = '4043307'

PASSWORD_HASHERS = (
    'django.contrib.auth.hashers.MD5PasswordHasher',
)

SQL_RESET_SEQUENCES = False
GEOIP_URL = ''
GEOIP_DEFAULT_VAL = 'restofworld'
GEOIP_DEFAULT_TIMEOUT = .2

ES_DEFAULT_NUM_REPLICAS = 0
ES_DEFAULT_NUM_SHARDS = 3

IARC_MOCK = True

# Ensure that exceptions aren't re-raised.
DEBUG_PROPAGATE_EXCEPTIONS = False

PAYMENT_PROVIDERS = ['bango']

# When not testing this specific feature, make sure it's off.
PRE_GENERATE_APKS = False
# This is a precaution in case something isn't mocked right.
PRE_GENERATE_APK_URL = 'http://you-should-never-load-this.com/'

# A sample key for signing receipts.
WEBAPPS_RECEIPT_KEY = os.path.join(ROOT, 'mkt/webapps/tests/sample.key')
