"""private_mkt will be populated from puppet and placed in this directory"""

from mkt.settings import *  # noqa
from settings_base import *  # noqa

import private_mkt

DOMAIN = "marketplace-altdev.allizom.org"
SERVER_EMAIL = 'zmarketplacedev@addons.mozilla.org'

SITE_URL = 'https://marketplace-altdev.allizom.org'
BROWSERID_AUDIENCES = [SITE_URL, 'localhost', 'localhost:8675']
STATIC_URL = os.getenv('CUSTOM_CDN',
                       'https://marketplace-altdev-cdn.allizom.org/')

LOCAL_MIRROR_URL = '%s_files' % STATIC_URL

CSP_SCRIPT_SRC = CSP_SCRIPT_SRC + (STATIC_URL[:-1],)

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_DOMAIN = ".%s" % DOMAIN

MEDIA_URL = STATIC_URL + 'media/'

CACHE_PREFIX = 'altdev.mkt.%s' % CACHE_PREFIX
CACHE_MIDDLEWARE_KEY_PREFIX = CACHE_PREFIX
CACHES['default']['KEY_PREFIX'] = CACHE_PREFIX

SYSLOG_TAG = "http_app_mkt_altdev"
SYSLOG_TAG2 = "http_app_mkt_altdev_timer"
SYSLOG_CSP = "http_app_mkt_altdev_csp"

STATSD_PREFIX = 'marketplace-dev'

# Celery
BROKER_URL = private_mkt.BROKER_URL

CELERY_ALWAYS_EAGER = False
CELERY_IGNORE_RESULT = True
CELERY_DISABLE_RATE_LIMITS = True
CELERYD_PREFETCH_MULTIPLIER = 1

WEBAPPS_RECEIPT_KEY = private_mkt.WEBAPPS_RECEIPT_KEY
WEBAPPS_RECEIPT_URL = private_mkt.WEBAPPS_RECEIPT_URL

WEBAPPS_UNIQUE_BY_DOMAIN = False

SENTRY_DSN = private_mkt.SENTRY_DSN

WEBAPPS_PUBLIC_KEY_DIRECTORY = NETAPP_STORAGE + '/public_keys'
PRODUCT_ICON_PATH = NETAPP_STORAGE + '/product-icons'
DUMPED_APPS_PATH = NETAPP_STORAGE + '/dumped-apps'
DUMPED_USERS_PATH = NETAPP_STORAGE + '/dumped-users'

SOLITUDE_HOSTS = ('https://payments-dev.allizom.org',)
SOLITUDE_OAUTH = {'key': private_mkt.SOLITUDE_OAUTH_KEY,
                  'secret': private_mkt.SOLITUDE_OAUTH_SECRET}

VALIDATOR_TIMEOUT = 180
VALIDATOR_IAF_URLS = ['https://marketplace.firefox.com',
                      'https://marketplace.allizom.org',
                      'https://marketplace-dev.allizom.org',
                      'https://marketplace-altdev.allizom.org']

# Override the limited marketplace ones with these ones from AMO. Because
# the base gets overridden in the mkt.settings file, we'll set them back again.
# Note the addition of dbg here.
AMO_LANGUAGES = AMO_LANGUAGES + ('dbg', 'rtl')
LANGUAGES = lazy(langs, dict)(AMO_LANGUAGES)
LANGUAGE_URL_MAP = dict([(i.lower(), i) for i in AMO_LANGUAGES])

# Bug 748403
SIGNING_SERVER = private_mkt.SIGNING_SERVER
SIGNING_SERVER_ACTIVE = True
SIGNING_VALID_ISSUERS = ['marketplace-dev-cdn.allizom.org']

# Bug 793876
SIGNED_APPS_KEY = private_mkt.SIGNED_APPS_KEY
SIGNED_APPS_SERVER_ACTIVE = True
SIGNED_APPS_SERVER = private_mkt.SIGNED_APPS_SERVER
SIGNED_APPS_REVIEWER_SERVER_ACTIVE = True
SIGNED_APPS_REVIEWER_SERVER = private_mkt.SIGNED_APPS_REVIEWER_SERVER

GOOGLE_ANALYTICS_DOMAIN = 'marketplace.firefox.com'


# Pass through the DSN to the Raven client and force signal
# registration so that exceptions are passed through to sentry
# RAVEN_CONFIG = {'dsn': SENTRY_DSN, 'register_signals': True}

# See mkt/settings.py for more info.
APP_PURCHASE_KEY = DOMAIN
APP_PURCHASE_AUD = DOMAIN
APP_PURCHASE_TYP = 'mozilla-altdev/payments/pay/v1'
APP_PURCHASE_SECRET = private_mkt.APP_PURCHASE_SECRET

MONOLITH_PASSWORD = private_mkt.MONOLITH_PASSWORD

# This is mainly for Marionette tests.
WEBAPP_MANIFEST_NAME = 'Marketplace Dev'

ENABLE_API_ERROR_SERVICE = True

# Until Bango can properly do refunds.
BANGO_FAKE_REFUNDS = True

if NEWRELIC_ENABLE:
    NEWRELIC_INI = '/etc/newrelic.d/marketplace-altdev.allizom.org.ini'

ES_DEFAULT_NUM_REPLICAS = 2
ES_USE_PLUGINS = True

# Cache timeout on the /search/featured API.
CACHE_SEARCH_FEATURED_API_TIMEOUT = 60 * 5  # 5 min.

ALLOWED_CLIENTS_EMAIL_API = private_mkt.ALLOWED_CLIENTS_EMAIL_API

POSTFIX_AUTH_TOKEN = private_mkt.POSTFIX_AUTH_TOKEN

POSTFIX_DOMAIN = 'marketplace-dev.allizom.org'

MONOLITH_INDEX = 'mktdev-time_*'

# IARC content ratings.
IARC_ENV = 'test'
IARC_MOCK = False
IARC_PASSWORD = private_mkt.IARC_PASSWORD
IARC_PLATFORM = 'Firefox'
IARC_SERVICE_ENDPOINT = 'https://www.globalratings.com/IARCDEMOService/IARCServices.svc'  # noqa
IARC_STOREFRONT_ID = 4
IARC_SUBMISSION_ENDPOINT = 'https://www.globalratings.com/IARCDEMORating/Submission.aspx'  # noqa
IARC_ALLOW_CERT_REUSE = True

# We'll use zippy, the reference implementation on -dev.
PAYMENT_PROVIDERS = ['reference']

PRE_GENERATE_APK_URL = 'http://dapk.net/application.apk'

FXA_AUTH_DOMAIN = getattr(private_mkt, 'FXA_AUTH_DOMAIN', '')
FXA_OAUTH_URL = getattr(private_mkt, 'FXA_OAUTH_URL', '')
FXA_CLIENT_ID = getattr(private_mkt, 'FXA_CLIENT_ID', '')
FXA_CLIENT_SECRET = getattr(private_mkt, 'FXA_CLIENT_SECRET', '')
FXA_SECRETS = {
    FXA_CLIENT_ID: FXA_CLIENT_SECRET,
}

# Bug 1145338
IAF_OVERRIDE_APPS = private_mkt.IAF_OVERRIDE_APPS

DEV_PAY_PROVIDERS = {
    APP_PURCHASE_TYP: SITE_URL + '/mozpay/?req={jwt}',
}
