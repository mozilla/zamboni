import atexit
import tempfile

from mkt.settings import *  # noqa


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


# Various paths. See mkt/settings.py for documentation:
NETAPP_STORAGE = _polite_tmpdir()
ADDONS_PATH = _polite_tmpdir()
ADDON_ICONS_PATH = _polite_tmpdir()
WEBSITE_ICONS_PATH = _polite_tmpdir()
GUARDED_ADDONS_PATH = _polite_tmpdir()
SIGNED_APPS_PATH = _polite_tmpdir()
SIGNED_APPS_REVIEWER_PATH = _polite_tmpdir()
SIGNING_SERVER_ACTIVE = False
UPLOADS_PATH = _polite_tmpdir()
TMP_PATH = _polite_tmpdir()
REVIEWER_ATTACHMENTS_PATH = _polite_tmpdir()
DUMPED_APPS_PATH = _polite_tmpdir()


ALLOW_SELF_REVIEWS = True
BROWSERID_AUDIENCES = [SITE_URL]
# COUNT() caching can't be invalidated, it just expires after x seconds. This
# is just too annoying for tests, so disable it.
CACHE_COUNT_TIMEOUT = -1
CELERY_ROUTES = {}
CELERY_ALWAYS_EAGER = True
DEBUG = False
DEBUG_PROPAGATE_EXCEPTIONS = False
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
ES_DEFAULT_NUM_REPLICAS = 0
# See the following URL on why we set num_shards to 1 for tests:
# http://www.elasticsearch.org/guide/en/elasticsearch/guide/current/relevance-is-broken.html
ES_DEFAULT_NUM_SHARDS = 1
IARC_MOCK = True
IN_TEST_SUITE = True
INSTALLED_APPS += ('mkt.translations.tests.testapp',)
PASSWORD_HASHERS = (
    'django.contrib.auth.hashers.MD5PasswordHasher',
)
PAYMENT_PROVIDERS = ['bango', 'reference']
# This is a precaution in case something isn't mocked right.
PRE_GENERATE_APK_URL = 'http://you-should-never-load-this.com/'
RUN_ES_TESTS = True
SEND_REAL_EMAIL = True
SITE_URL = 'http://testserver'
STATIC_URL = SITE_URL + '/'
TASK_USER_ID = '4043307'
TEMPLATE_DEBUG = False
VIDEO_LIBRARIES = ['lib.video.dummy']
