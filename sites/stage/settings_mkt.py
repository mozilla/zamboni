"""private_mkt will be populated from puppet and placed in this directory"""

from mkt.settings import *  # noqa
from settings_base import *  # noqa

import private_mkt

DOMAIN = 'marketplace.allizom.org'
SERVER_EMAIL = 'zmarketplacestage@addons.mozilla.org'

DOMAIN = "marketplace.allizom.org"
SITE_URL = 'https://marketplace.allizom.org'
BROWSERID_AUDIENCES = [SITE_URL]
STATIC_URL = os.getenv('CUSTOM_CDN', 'https://marketplace-cdn.allizom.org/')
LOCAL_MIRROR_URL = '%s_files' % STATIC_URL

CSP_SCRIPT_SRC = CSP_SCRIPT_SRC + (STATIC_URL[:-1],)

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_DOMAIN = ".%s" % DOMAIN

MEDIA_URL = STATIC_URL + 'media/'

CACHE_PREFIX = 'stage.mkt.%s' % CACHE_PREFIX
CACHE_MIDDLEWARE_KEY_PREFIX = CACHE_PREFIX
CACHES['default']['KEY_PREFIX'] = CACHE_PREFIX

CACHE_MACHINE_ENABLED = True

LOG_LEVEL = logging.DEBUG
# The django statsd client to use, see django-statsd for more.
# STATSD_CLIENT = 'django_statsd.clients.moz_heka'

SYSLOG_TAG = "http_app_mkt_stage"
SYSLOG_TAG2 = "http_app_mkt_stage_timer"
SYSLOG_CSP = "http_app_mkt_stage_csp"
STATSD_PREFIX = 'marketplace-stage'

# Celery
BROKER_URL = private_mkt.BROKER_URL

CELERY_ALWAYS_EAGER = False
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
                      'https://marketplace-dev.allizom.org',
                      'https://marketplace-altdev.allizom.org']

if getattr(private_mkt, 'LOAD_TESTING', False):
    # mock the authentication and use django_fakeauth for this
    AUTHENTICATION_BACKENDS = (
        ('django_fakeauth.FakeAuthBackend',) + AUTHENTICATION_BACKENDS)
    MIDDLEWARE_CLASSES.insert(
        MIDDLEWARE_CLASSES.index('mkt.access.middleware.ACLMiddleware'),
        'django_fakeauth.FakeAuthMiddleware')
    FAKEAUTH_TOKEN = private_mkt.FAKEAUTH_TOKEN

    # we are also creating access tokens for OAuth, here are the keys and
    # secrets used for them
    API_PASSWORD = getattr(private_mkt, 'API_PASSWORD', FAKEAUTH_TOKEN)

AMO_LANGUAGES = AMO_LANGUAGES + ('dbg', 'rtl', 'ar', 'ln', 'sw', 'tl')
LANGUAGES = lazy(langs, dict)(AMO_LANGUAGES)
LANGUAGE_URL_MAP = dict([(i.lower(), i) for i in AMO_LANGUAGES])

# Bug 748403
SIGNING_SERVER = private_mkt.SIGNING_SERVER
SIGNING_SERVER_ACTIVE = True
SIGNING_VALID_ISSUERS = ['marketplace-cdn.allizom.org']

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
WEBAPP_MANIFEST_NAME = 'Marketplace Stage'

ENABLE_API_ERROR_SERVICE = True

NEWRELIC_INI = '/etc/newrelic.d/marketplace.allizom.org.ini'

ES_DEFAULT_NUM_REPLICAS = 2
ES_USE_PLUGINS = True

BANGO_BASE_PORTAL_URL = 'https://mozilla.bango.com/login/al.aspx?'

ALLOWED_CLIENTS_EMAIL_API = private_mkt.ALLOWED_CLIENTS_EMAIL_API

POSTFIX_AUTH_TOKEN = private_mkt.POSTFIX_AUTH_TOKEN

POSTFIX_DOMAIN = DOMAIN

MONOLITH_INDEX = 'mktstage-time_*'

# IARC content ratings.
IARC_ENV = 'test'
IARC_MOCK = False
IARC_PASSWORD = private_mkt.IARC_PASSWORD
IARC_PLATFORM = 'Firefox'
IARC_SERVICE_ENDPOINT = 'https://www.globalratings.com/IARCDEMOService/IARCServices.svc'  # noqa

IARC_STOREFRONT_ID = 4
IARC_SUBMISSION_ENDPOINT = 'https://www.globalratings.com/IARCDEMORating/Submission.aspx'  # noqa

IARC_ALLOW_CERT_REUSE = True

PRE_GENERATE_APKS = True
PRE_GENERATE_APK_URL = \
    'https://apk-controller.stage.mozaws.net/application.apk'

FXA_AUTH_DOMAIN = 'api.accounts.firefox.com'
FXA_OAUTH_URL = 'https://oauth.accounts.firefox.com'
FXA_CLIENT_ID = getattr(private_mkt, 'FXA_CLIENT_ID', '')
FXA_CLIENT_SECRET = getattr(private_mkt, 'FXA_CLIENT_SECRET', '')
FXA_SECRETS = {
    FXA_CLIENT_ID: FXA_CLIENT_SECRET,
}

DEFAULT_PAYMENT_PROVIDER = 'bango'
PAYMENT_PROVIDERS = ['bango']

RECOMMENDATIONS_API_URL = 'https://recommend.allizom.org'
RECOMMENDATIONS_ENABLED = True

QA_APP_ID = 500427

DEV_PAY_PROVIDERS = {
    APP_PURCHASE_TYP: SITE_URL + '/mozpay/?req={jwt}',
}

# Bug 1145338
IAF_OVERRIDE_APPS = private_mkt.IAF_OVERRIDE_APPS
