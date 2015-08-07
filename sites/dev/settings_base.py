"""private_base will be populated from puppet and placed in this directory"""

import logging
import os

import dj_database_url

from mkt.settings import (CACHE_PREFIX, ES_INDEXES,
                          KNOWN_PROXIES, LOGGING, HOSTNAME)

from .. import splitstrip
import private_base as private

ALLOWED_HOSTS = ['.allizom.org', '.mozflare.net']

ENGAGE_ROBOTS = False

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = private.EMAIL_HOST

DEBUG = False
TEMPLATE_DEBUG = DEBUG
DEBUG_PROPAGATE_EXCEPTIONS = False
SESSION_COOKIE_SECURE = True

ADMINS = ()

DATABASES = {}
DATABASES['default'] = dj_database_url.parse(private.DATABASES_DEFAULT_URL)
DATABASES['default']['ENGINE'] = 'django.db.backends.mysql'
DATABASES['default']['OPTIONS'] = {'init_command': 'SET storage_engine=InnoDB'}
DATABASES['default']['ATOMIC_REQUESTS'] = True
DATABASES['default']['CONN_MAX_AGE'] = 5 * 60  # 5m for persistent connections.

DATABASES['slave'] = dj_database_url.parse(private.DATABASES_SLAVE_URL)
DATABASES['slave']['ENGINE'] = 'django.db.backends.mysql'
DATABASES['slave']['OPTIONS'] = {'init_command': 'SET storage_engine=InnoDB'}
DATABASES['slave']['sa_pool_key'] = 'slave'
DATABASES['slave']['ATOMIC_REQUESTS'] = True
DATABASES['slave']['CONN_MAX_AGE'] = 5 * 60  # 5m for persistent connections.

SERVICES_DATABASE = dj_database_url.parse(private.SERVICES_DATABASE_URL)

SLAVE_DATABASES = ['slave']

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.memcached.MemcachedCache',
        'LOCATION': splitstrip(private.CACHES_DEFAULT_LOCATION),
        'TIMEOUT': 500,
        'KEY_PREFIX': CACHE_PREFIX,
    }
}

SECRET_KEY = private.SECRET_KEY

LOG_LEVEL = logging.DEBUG

# Celery
BROKER_URL = private.BROKER_URL

CELERY_ALWAYS_EAGER = False
CELERY_IGNORE_RESULT = True
CELERY_DISABLE_RATE_LIMITS = True
CELERYD_PREFETCH_MULTIPLIER = 1

NETAPP_STORAGE = private.NETAPP_STORAGE_ROOT + '/shared_storage'
GUARDED_ADDONS_PATH = private.NETAPP_STORAGE_ROOT + '/guarded-addons'
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

ADDONS_PATH = private.NETAPP_STORAGE_ROOT + '/files'

SPIDERMONKEY = '/usr/bin/tracemonkey'

csp = 'csp.middleware.CSPMiddleware'


RESPONSYS_ID = private.RESPONSYS_ID

CRONJOB_LOCK_PREFIX = 'mkt-dev'

ES_DEFAULT_NUM_REPLICAS = 2
ES_HOSTS = splitstrip(private.ES_HOSTS)
ES_URLS = ['http://%s' % h for h in ES_HOSTS]
ES_INDEXES = dict((k, '%s_dev' % v) for k, v in ES_INDEXES.items())

STATSD_HOST = private.STATSD_HOST
STATSD_PORT = private.STATSD_PORT
STATSD_PREFIX = private.STATSD_PREFIX

CEF_PRODUCT = STATSD_PREFIX

ES_TIMEOUT = 60

EXPOSE_VALIDATOR_TRACEBACKS = False

KNOWN_PROXIES += ['10.2.83.105',
                  '10.2.83.106',
                  '10.2.83.107',
                  '10.8.83.200',
                  '10.8.83.201',
                  '10.8.83.202',
                  '10.8.83.203',
                  '10.8.83.204',
                  '10.8.83.210',
                  '10.8.83.211',
                  '10.8.83.212',
                  '10.8.83.213',
                  '10.8.83.214',
                  '10.8.83.215',
                  '10.8.83.251',
                  '10.8.83.252',
                  '10.8.83.253',
                  ]

NEW_FEATURES = True

CLEANCSS_BIN = 'cleancss'
LESS_BIN = 'lessc'
STYLUS_BIN = 'stylus'
UGLIFY_BIN = 'uglifyjs'

CELERYD_TASK_SOFT_TIME_LIMIT = 540
VALIDATOR_TIMEOUT = 180

LESS_PREPROCESS = True

XSENDFILE = True

ALLOW_SELF_REVIEWS = True

GOOGLE_ANALYTICS_CREDENTIALS = private.GOOGLE_ANALYTICS_CREDENTIALS
GOOGLE_API_CREDENTIALS = private.GOOGLE_API_CREDENTIALS

MONOLITH_SERVER = 'https://monolith-dev.allizom.org'

GEOIP_URL = 'https://geo-dev-marketplace.allizom.org'

AWS_ACCESS_KEY_ID = private.AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY = private.AWS_SECRET_ACCESS_KEY
AWS_STORAGE_BUCKET_NAME = private.AWS_STORAGE_BUCKET_NAME

RAISE_ON_SIGNAL_ERROR = True

API_THROTTLE = False

NEWRELIC_ENABLED_LIST = ['dev1.addons.phx1.mozilla.com',
                         'dev2.addons.phx1.mozilla.com']

NEWRELIC_ENABLE = HOSTNAME in NEWRELIC_ENABLED_LIST

AES_KEYS = private.AES_KEYS

TASK_USER_ID = 4757633
SERVE_TMP_PATH = False
