from mkt.settings import *  # noqa
import logging
import environ

environ.Env.read_env(env_file='/etc/zamboni/settings.env')
env = environ.Env()

ENV = env('ENV')
DOMAIN = env('DOMAIN')
SITE_URL = 'https://{0}'.format(DOMAIN)
CRONJOB_LOCK_PREFIX = DOMAIN

BROWSERID_AUDIENCES = [SITE_URL, 'localhost', 'localhost:8675']

STATIC_URL = env('STATIC_URL')

LOCAL_MIRROR_URL = '%s_files' % STATIC_URL

ADMINS = ()
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS')

DEBUG = False
DEBUG_PROPAGATE_EXCEPTIONS = False
EMAIL_URL = env.email_url('EMAIL_URL')
EMAIL_HOST = EMAIL_URL['EMAIL_HOST']
EMAIL_PORT = EMAIL_URL['EMAIL_PORT']
EMAIL_BACKEND = EMAIL_URL['EMAIL_BACKEND']
EMAIL_HOST_USER = EMAIL_URL['EMAIL_HOST_USER']
EMAIL_HOST_PASSWORD = EMAIL_URL['EMAIL_HOST_PASSWORD']

ENGAGE_ROBOTS = False
SERVER_EMAIL = env('SERVER_EMAIL')
SESSION_COOKIE_SECURE = True
TEMPLATE_DEBUG = DEBUG

DATABASES = {}
DATABASES['default'] = env.db('DATABASES_DEFAULT_URL')
DATABASES['default']['ENGINE'] = 'django.db.backends.mysql'
DATABASES['default']['OPTIONS'] = {'init_command': 'SET storage_engine=InnoDB'}
DATABASES['default']['ATOMIC_REQUESTS'] = True
DATABASES['default']['CONN_MAX_AGE'] = 5 * 60  # 5m for persistent connections.

DATABASES['slave'] = env.db('DATABASES_SLAVE_URL')
DATABASES['slave']['ENGINE'] = 'django.db.backends.mysql'
DATABASES['slave']['OPTIONS'] = {'init_command': 'SET storage_engine=InnoDB'}
DATABASES['slave']['sa_pool_key'] = 'slave'
DATABASES['slave']['ATOMIC_REQUESTS'] = True
DATABASES['slave']['CONN_MAX_AGE'] = 5 * 60  # 5m for persistent connections.

SERVICES_DATABASE = env.db('SERVICES_DATABASE_URL')
SLAVE_DATABASES = ['slave']

CACHE_PREFIX = 'mkt.%s' % ENV

CACHES = {}
CACHES['default'] = env.cache('CACHES_DEFAULT')
CACHES['default']['TIMEOUT'] = 500
CACHES['default']['KEY_PREFIX'] = CACHE_PREFIX

SECRET_KEY = env('SECRET_KEY')

# Celery
BROKER_URL = env('BROKER_URL')

CELERY_ALWAYS_EAGER = False
CELERYD_PREFETCH_MULTIPLIER = 1

NETAPP_STORAGE = env('NETAPP_STORAGE_ROOT') + '/shared_storage'
GUARDED_ADDONS_PATH = env('NETAPP_STORAGE_ROOT') + '/guarded-addons'
UPLOADS_PATH = NETAPP_STORAGE + '/uploads'
ADDON_ICONS_PATH = UPLOADS_PATH + '/addon_icons'
WEBSITE_ICONS_PATH = UPLOADS_PATH + '/website_icons'
FEATURED_APP_BG_PATH = UPLOADS_PATH + '/featured_app_background'
FEED_COLLECTION_BG_PATH = UPLOADS_PATH + '/feed_collection_background'
FEED_SHELF_BG_PATH = UPLOADS_PATH + '/feed_shelf_background'
IMAGEASSETS_PATH = UPLOADS_PATH + '/imageassets'
REVIEWER_ATTACHMENTS_PATH = UPLOADS_PATH + '/reviewer_attachment'
PREVIEWS_PATH = UPLOADS_PATH + '/previews'
WEBAPP_PROMO_IMG_PATH = UPLOADS_PATH + '/webapp_promo_imgs'
WEBSITE_PROMO_IMG_PATH = UPLOADS_PATH + '/website_promo_imgs'
SIGNED_APPS_PATH = NETAPP_STORAGE + '/signed_apps'
SIGNED_APPS_REVIEWER_PATH = NETAPP_STORAGE + '/signed_apps_reviewer'
PREVIEW_THUMBNAIL_PATH = PREVIEWS_PATH + '/thumbs/%s/%d.png'
PREVIEW_FULL_PATH = PREVIEWS_PATH + '/full/%s/%d.%s'
EXTENSIONS_PATH = NETAPP_STORAGE + '/extensions'
SIGNED_EXTENSIONS_PATH = NETAPP_STORAGE + '/signed-extensions'


LOGGING['loggers'].update({
    'amqp': {'level': logging.WARNING},
    'raven': {'level': logging.WARNING},
    'requests': {'level': logging.WARNING},
    'z.addons': {'level': logging.DEBUG},
    'z.elasticsearch': {'level': logging.DEBUG},
    'z.pool': {'level': logging.ERROR},
    'z.task': {'level': logging.DEBUG},
    'z.users': {'level': logging.DEBUG},
})

TMP_PATH = os.path.join(NETAPP_STORAGE, 'tmp')
ADDONS_PATH = env('NETAPP_STORAGE_ROOT') + '/files'

SPIDERMONKEY = '/usr/bin/tracemonkey'
csp = 'csp.middleware.CSPMiddleware'

RESPONSYS_ID = env('RESPONSYS_ID')

ES_DEFAULT_NUM_REPLICAS = 2
ES_HOSTS = env('ES_HOSTS')
ES_URLS = ['http://%s' % h for h in ES_HOSTS]
ES_INDEXES = dict((k, '%s_%s' % (v, ENV)) for k, v in ES_INDEXES.items())

STATSD_HOST = env('STATSD_HOST')
STATSD_PORT = env.int('STATSD_PORT', default=8125)
STATSD_PREFIX = 'mkt-{0}'.format(ENV)

CEF_PRODUCT = STATSD_PREFIX

EXPOSE_VALIDATOR_TRACEBACKS = False

NEW_FEATURES = True

CELERYD_TASK_SOFT_TIME_LIMIT = env.int('CELERYD_TASK_SOFT_TIME_LIMIT',
                                       default=540)

XSENDFILE = True

# False in Prod
ALLOW_SELF_REVIEWS = env.bool('ALLOW_SELF_REVIEWS', default=False)

GOOGLE_ANALYTICS_CREDENTIALS = env.dict('GOOGLE_ANALYTICS_CREDENTIALS')
GOOGLE_ANALYTICS_CREDENTIALS['user_agent'] = None
GOOGLE_ANALYTICS_CREDENTIALS['token_expiry'] = datetime.datetime(2013, 1, 3, 1, 20, 16, 45465)  # noqa
GOOGLE_API_CREDENTIALS = env('GOOGLE_API_CREDENTIALS')

GEOIP_URL = env('GEOIP_URL')

RAISE_ON_SIGNAL_ERROR = True

API_THROTTLE = False

NEWRELIC_ENABLED_LIST = env.list('NEWRELIC_ENABLED_LIST')

NEWRELIC_ENABLE = HOSTNAME in NEWRELIC_ENABLED_LIST

AES_KEYS = env.dict('AES_KEYS')

TASK_USER_ID = env('TASK_USER_ID', default=4757633)
SERVE_TMP_PATH = False

CSP_SCRIPT_SRC = CSP_SCRIPT_SRC + (STATIC_URL.rstrip('/'),)

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_DOMAIN = ".%s" % DOMAIN

MEDIA_URL = STATIC_URL + 'media/'

CACHE_MIDDLEWARE_KEY_PREFIX = CACHE_PREFIX

SYSLOG_TAG = "http_app_mkt_{0}".format(ENV)
SYSLOG_TAG2 = "http_app_mkt_{0}_timer".format(ENV)
SYSLOG_CSP = "http_app_mkt_{0}csp".format(ENV)

STATSD_PREFIX = 'marketplace-{0}'.format(ENV)

WEBAPPS_RECEIPT_KEY = env('WEBAPPS_RECEIPT_KEY')
WEBAPPS_RECEIPT_URL = env('WEBAPPS_RECEIPT_URL')

WEBAPPS_UNIQUE_BY_DOMAIN = env.bool('WEBAPPS_UNIQUE_BY_DOMAIN', default=False)

SENTRY_DSN = env('SENTRY_DSN')

WEBAPPS_PUBLIC_KEY_DIRECTORY = NETAPP_STORAGE + '/public_keys'
PRODUCT_ICON_PATH = NETAPP_STORAGE + '/product-icons'
DUMPED_APPS_PATH = NETAPP_STORAGE + '/dumped-apps'
DUMPED_USERS_PATH = NETAPP_STORAGE + '/dumped-users'

SOLITUDE_HOSTS = (env('SOLITUDE_HOSTS'),)
SOLITUDE_OAUTH = {'key': env('SOLITUDE_OAUTH_KEY'),
                  'secret': env('SOLITUDE_OAUTH_SECRET')}

VALIDATOR_TIMEOUT = env.int('VALIDATOR_TIMEOUT', default=180)

VALIDATOR_IAF_URLS = ['https://marketplace.firefox.com',
                      'https://marketplace.allizom.org',
                      'https://marketplace-dev.allizom.org']

# Override the limited marketplace ones with these ones from AMO. Because
# the base gets overridden in the mkt.settings file, we'll set them back again.
# Note the addition of the testing locales dbg and rtl here.
AMO_LANGUAGES = AMO_LANGUAGES + ('dbg', 'rtl', 'ln', 'tl')
LANGUAGES = lazy(langs, dict)(AMO_LANGUAGES)
LANGUAGE_URL_MAP = dict([(i.lower(), i) for i in AMO_LANGUAGES])

# Bug 748403
SIGNING_SERVER = env('SIGNING_SERVER')
SIGNING_SERVER_ACTIVE = True
SIGNING_VALID_ISSUERS = ['marketplace-dev-cdn.allizom.org']

# Bug 793876
SIGNED_APPS_KEY = env('SIGNED_APPS_KEY')
SIGNED_APPS_SERVER_ACTIVE = True
SIGNED_APPS_SERVER = env('SIGNED_APPS_SERVER')
SIGNED_APPS_REVIEWER_SERVER_ACTIVE = True
SIGNED_APPS_REVIEWER_SERVER = env('SIGNED_APPS_REVIEWER_SERVER')

GOOGLE_ANALYTICS_DOMAIN = 'marketplace.firefox.com'

# See mkt/settings.py for more info.
APP_PURCHASE_KEY = DOMAIN
APP_PURCHASE_AUD = DOMAIN
APP_PURCHASE_TYP = 'mozilla-dev/payments/pay/v1'
APP_PURCHASE_SECRET = env('APP_PURCHASE_SECRET')

MONOLITH_PASSWORD = env('MONOLITH_PASSWORD')
MONOLITH_SERVER = env('MONOLITH_SERVER')
MONOLITH_INDEX = 'mkt{0}-time_*'.format(ENV)

# This is mainly for Marionette tests.
WEBAPP_MANIFEST_NAME = env('WEBAPP_MANIFEST_NAME', default='Marketplace Dev')

ENABLE_API_ERROR_SERVICE = env.bool('ENABLE_API_ERROR_SERVICE', default=True)

# Until Bango can properly do refunds.
BANGO_FAKE_REFUNDS = env.bool('BANGO_FAKE_REFUNDS', default=True)

if NEWRELIC_ENABLE:
    NEWRELIC_INI = '/etc/newrelic.d/{0}.ini'.format(DOMAIN)

ES_DEFAULT_NUM_REPLICAS = 2
ES_USE_PLUGINS = True

# Cache timeout on the /search/featured API.
CACHE_SEARCH_FEATURED_API_TIMEOUT = 60 * 5  # 5 min.

ALLOWED_CLIENTS_EMAIL_API = env.list('ALLOWED_CLIENTS_EMAIL_API')

POSTFIX_AUTH_TOKEN = env('POSTFIX_AUTH_TOKEN')

POSTFIX_DOMAIN = DOMAIN

# IARC content ratings.
IARC_ENV = env('IARC_ENV', default='test')
IARC_MOCK = False
IARC_PASSWORD = env('IARC_PASSWORD')
IARC_PLATFORM = env('IARC_PLATFORM', default='Firefox')
IARC_SERVICE_ENDPOINT = 'https://www.globalratings.com/IARCDEMOService/IARCServices.svc'  # noqa
IARC_STOREFRONT_ID = env('IARC_STOREFRONT_ID', default=4)
IARC_SUBMISSION_ENDPOINT = 'https://www.globalratings.com/IARCDEMORating/Submission.aspx'  # noqa
IARC_ALLOW_CERT_REUSE = True

# We'll use zippy, the reference implementation on -dev.
PAYMENT_PROVIDERS = env.list('PAYMENT_PROVIDERS', default=['reference'])

# Since Bango won't actually work on -dev anyway, may as well make it the
# reference implementation anyway.
DEFAULT_PAYMENT_PROVIDER = env('DEFAULT_PAYMENT_PROVIDER', default='reference')

PRE_GENERATE_APKS = True
PRE_GENERATE_APK_URL = env('PRE_GENERATE_APK_URL')

FXA_AUTH_DOMAIN = env('FXA_AUTH_DOMAIN')
FXA_OAUTH_URL = env('FXA_OAUTH_URL')
FXA_CLIENT_ID = env('FXA_CLIENT_ID')
FXA_CLIENT_SECRET = env('FXA_CLIENT_SECRET')
FXA_SECRETS[FXA_CLIENT_ID] = FXA_CLIENT_SECRET

RECOMMENDATIONS_API_URL = env('RECOMMENDATIONS_API_URL')
RECOMMENDATIONS_ENABLED = True

DEV_PAY_PROVIDERS = {
    APP_PURCHASE_TYP: SITE_URL + '/mozpay/?req={jwt}',
}

# Bug 1145338
IAF_OVERRIDE_APPS = env.list('IAF_OVERRIDE_APPS')
