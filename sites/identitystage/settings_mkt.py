"""private_mkt will be populated from puppet and placed in this directory"""

from mkt.settings import *  # noqa
from settings_base import *  # noqa

import private_mkt

DOMAIN = 'identity-stage-marketplace.allizom.org'
SERVER_EMAIL = 'zmarketplacestage@addons.mozilla.org'

SITE_URL = 'https://identity-stage-marketplace.allizom.org'
BROWSERID_AUDIENCES = [SITE_URL]
STATIC_URL = 'https://identity-stage-marketplace-cdn.allizom.org/'
LOCAL_MIRROR_URL = '%s_files' % STATIC_URL

CSP_SCRIPT_SRC = CSP_SCRIPT_SRC + (STATIC_URL[:-1],)

BROWSERID_DOMAIN = 'login.anosrep.org'
BROWSERID_VERIFICATION_URL = 'https://verifier.login.anosrep.org/verify'
BROWSERID_JS_URL = 'https://login.anosrep.org/include.js'
NATIVE_BROWSERID_DOMAIN = 'firefoxos.anosrep.org'
UNVERIFIED_ISSUER = 'firefoxos.anosrep.org'

# This is a B2G (or other native) verifier. Adjust accordingly.
NATIVE_BROWSERID_VERIFICATION_URL = ('https://%s/verify'
                                     % NATIVE_BROWSERID_DOMAIN)
NATIVE_BROWSERID_JS_URL = ('https://%s/include.js'
                           % NATIVE_BROWSERID_DOMAIN)

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_DOMAIN = ".%s" % DOMAIN

MEDIA_URL = STATIC_URL + 'media/'

CACHE_PREFIX = 'identity.stage.mkt.%s' % CACHE_PREFIX
CACHE_MIDDLEWARE_KEY_PREFIX = CACHE_PREFIX

CACHES['default']['KEY_PREFIX'] = CACHE_PREFIX


LOG_LEVEL = logging.DEBUG
# The django statsd client to use, see django-statsd for more.

SYSLOG_TAG = "http_app_marketplace_identity_stage"
SYSLOG_TAG2 = "http_app_marketplace_identity_stage_timer"
SYSLOG_CSP = "http_app_marketplace_identity_stage_csp"
STATSD_PREFIX = 'marketplace-identity-stage'

# Celery
BROKER_URL = private_mkt.BROKER_URL

CELERY_ALWAYS_EAGER = True
CELERY_IGNORE_RESULT = True
CELERY_DISABLE_RATE_LIMITS = True
CELERYD_PREFETCH_MULTIPLIER = 1

WEBAPPS_RECEIPT_KEY = private_mkt.WEBAPPS_RECEIPT_KEY
WEBAPPS_RECEIPT_URL = private_mkt.WEBAPPS_RECEIPT_URL

WEBAPPS_UNIQUE_BY_DOMAIN = True

SENTRY_DSN = private_mkt.SENTRY_DSN

SOLITUDE_HOSTS = ('https://payments.allizom.org',)
SOLITUDE_OAUTH = {'key': private_mkt.SOLITUDE_OAUTH_KEY,
                  'secret': private_mkt.SOLITUDE_OAUTH_SECRET}

WEBAPPS_PUBLIC_KEY_DIRECTORY = NETAPP_STORAGE + '/public_keys'
PRODUCT_ICON_PATH = NETAPP_STORAGE + '/product-icons'
DUMPED_APPS_PATH = NETAPP_STORAGE + '/dumped-apps'
DUMPED_USERS_PATH = NETAPP_STORAGE + '/dumped-users'

GOOGLE_ANALYTICS_DOMAIN = 'marketplace.firefox.com'

VALIDATOR_TIMEOUT = 180
VALIDATOR_IAF_URLS = ['https://marketplace.firefox.com',
                      'https://marketplace.allizom.org',
                      'https://identity-stage-marketplace.allizom.org',
                      'https://marketplace-dev.allizom.org',
                      'https://marketplace-altdev.allizom.org']

if getattr(private_mkt, 'LOAD_TESTING', False):
    # mock the authentication and use django_fakeauth for this
    AUTHENTICATION_BACKENDS = (
        ('django_fakeauth.FakeAuthBackend',) + AUTHENTICATION_BACKENDS
    )
    MIDDLEWARE_CLASSES.insert(
        MIDDLEWARE_CLASSES.index('mkt.access.middleware.ACLMiddleware'),
        'django_fakeauth.FakeAuthMiddleware')
    FAKEAUTH_TOKEN = private_mkt.FAKEAUTH_TOKEN

    # we are also creating access tokens for OAuth, here are the keys and
    # secrets used for them
    API_PASSWORD = getattr(private_mkt, 'API_PASSWORD', FAKEAUTH_TOKEN)
AMO_LANGUAGES = AMO_LANGUAGES + ('dbg',)
LANGUAGES = lazy(langs, dict)(AMO_LANGUAGES)
LANGUAGE_URL_MAP = dict([(i.lower(), i) for i in AMO_LANGUAGES])

# Bug 748403
SIGNING_SERVER = private_mkt.SIGNING_SERVER
SIGNING_SERVER_ACTIVE = True
SIGNING_VALID_ISSUERS = ['identity-stage-marketplace-cdn.allizom.org']

# Bug 793876
SIGNED_APPS_KEY = private_mkt.SIGNED_APPS_KEY
SIGNED_APPS_SERVER_ACTIVE = True
SIGNED_APPS_SERVER = private_mkt.SIGNED_APPS_SERVER
SIGNED_APPS_REVIEWER_SERVER_ACTIVE = True
SIGNED_APPS_REVIEWER_SERVER = private_mkt.SIGNED_APPS_REVIEWER_SERVER

# See mkt/settings.py for more info.
APP_PURCHASE_KEY = DOMAIN
APP_PURCHASE_AUD = DOMAIN
APP_PURCHASE_TYP = 'mozilla-stage/payments/pay/v1'
APP_PURCHASE_SECRET = private_mkt.APP_PURCHASE_SECRET

MONOLITH_PASSWORD = private_mkt.MONOLITH_PASSWORD

# This is mainly for Marionette tests.
WEBAPP_MANIFEST_NAME = 'Marketplace Identity Stage'

ENABLE_API_ERROR_SERVICE = True

ES_DEFAULT_NUM_REPLICAS = 2
ES_USE_PLUGINS = True

FXA_AUTH_DOMAIN = getattr(private_mkt, 'FXA_AUTH_DOMAIN', '')
FXA_OAUTH_URL = getattr(private_mkt, 'FXA_OAUTH_URL', '')
FXA_CLIENT_ID = getattr(private_mkt, 'FXA_CLIENT_ID', '')
FXA_CLIENT_SECRET = getattr(private_mkt, 'FXA_CLIENT_SECRET', '')
FXA_SECRETS = {
    FXA_CLIENT_ID: FXA_CLIENT_SECRET,
}

# Bug 1145338
IAF_OVERRIDE_APPS = private_mkt.IAF_OVERRIDE_APPS
