"""
Miscellaneous helpers that make Django compatible with AMO.
"""
import threading

import commonware.log

from mkt.constants.applications import *
from mkt.constants.base import *
from mkt.constants.payments import *
from mkt.constants.platforms import *
from mkt.constants.search import *

# This is used in multiple other files to access logging, do not remove.
from .log import (_LOG, LOG, LOG_BY_ID, LOG_ADMINS, LOG_EDITORS,
                  LOG_HIDE_DEVELOPER, LOG_KEEP, LOG_REVIEW_QUEUE,
                  LOG_REVIEW_EMAIL_USER, log)

logger_log = commonware.log.getLogger('z.amo')

_locals = threading.local()
_locals.user = None


def get_user():
    return getattr(_locals, 'user', None)


def set_user(user):
    _locals.user = user


# We need to import waffle here to avoid a circular import with jingo which
# loads all INSTALLED_APPS looking for helpers.py files, but some of those apps
# import jingo.
import waffle
