import logging
import logging.config
import os


# get the right settings module
settingmodule = os.environ.get('DJANGO_SETTINGS_MODULE', 'settings_local')
if settingmodule.startswith(('zamboni',  # typical git clone destination
                             'workspace',  # Jenkins
                             'project',  # vagrant VM
                             'freddo')):
    settingmodule = settingmodule.split('.', 1)[1]


import sys  # noqa

import MySQLdb as mysql  # noqa
import sqlalchemy.pool as pool  # noqa

from django.utils import importlib  # noqa
settings = importlib.import_module(settingmodule)

from mkt.constants.payments import (  # noqa
    CONTRIB_CHARGEBACK, CONTRIB_NO_CHARGE,
    CONTRIB_PURCHASE, CONTRIB_REFUND)

from lib.log_settings_base import formatters, handlers  # noqa


def getconn():
    db = settings.SERVICES_DATABASE
    return mysql.connect(host=db['HOST'], user=db['USER'],
                         passwd=db['PASSWORD'], db=db['NAME'])


mypool = pool.QueuePool(getconn, max_overflow=10, pool_size=5, recycle=300)


def log_configure():
    """You have to call this to explicity configure logging."""
    cfg = {
        'version': 1,
        'filters': {},
        'formatters': dict(prod=formatters['prod']),
        'handlers': dict(syslog=handlers['syslog']),
        'loggers': {
            'z': {'handlers': ['syslog'], 'level': logging.INFO},
        },
        'root': {},
        # Since this configuration is applied at import time
        # in verify.py we don't want it to clobber other logs
        # when imported into the marketplace Django app.
        'disable_existing_loggers': False,
    }
    logging.config.dictConfig(cfg)


def log_exception(data):
    # Note: although this logs exceptions, it logs at the info level so that
    # on prod, we log at the error level and result in no logs on prod.
    typ, value, discard = sys.exc_info()
    error_log = logging.getLogger('z.receipt')
    error_log.exception(u'Type: %s, %s. Data: %s' % (typ, value, data))


def log_info(msg):
    error_log = logging.getLogger('z.receipt')
    error_log.info(msg)
