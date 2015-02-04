import threading

from mkt.constants import (categories, comm, platforms, iarc_mappings,
                           ratingsbodies)  # flake8: noqa
from mkt.constants.applications import *  # flake8: noqa
from mkt.constants.base import *  # flake8: noqa
from mkt.constants.payments import *  # flake8: noqa
from mkt.constants.platforms import *  # flake8: noqa
from mkt.constants.search import *  # flake8: noqa
from mkt.constants.submit import *  # flake8: noqa

# This is used in multiple other files to access logging, do not remove.
from mkt.site.log import (_LOG, LOG, LOG_BY_ID, LOG_ADMINS, LOG_EDITORS,
                          LOG_HIDE_DEVELOPER, LOG_KEEP, LOG_REVIEW_QUEUE,
                          LOG_REVIEW_EMAIL_USER, log)  # flake8: noqa

_locals = threading.local()
_locals.user = None


def get_user():
    return getattr(_locals, 'user', None)


def set_user(user):
    _locals.user = user
