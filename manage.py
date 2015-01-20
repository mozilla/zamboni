#!/usr/bin/env python
import logging
import os
import sys

from django.core.management import execute_from_command_line

if not 'DJANGO_SETTINGS_MODULE' in os.environ:
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        os.environ['DJANGO_SETTINGS_MODULE'] = 'settings_test'
    else:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mkt.settings')

# waffle and mkt form an import cycle because mkt patches waffle and
# waffle loads the user model, so we have to make sure mkt gets
# imported before anything else imports waffle.
import mkt

import session_csrf
session_csrf.monkeypatch()

# Fix jinja's Markup class to not crash when localizers give us bad format
# strings.
from jinja2 import Markup
mod = Markup.__mod__
trans_log = logging.getLogger('z.trans')

# Load this early so that anything else you import will use these log settings.
# Mostly to shut Raven the hell up.
from lib.log_settings_base import log_configure
log_configure()

# We need to import waffle here to avoid a circular import with jingo which
# loads all INSTALLED_APPS looking for helpers.py files, but some of those apps
# import jingo.
import waffle

# Hardcore monkeypatching action.
import jingo.monkey
jingo.monkey.patch()


def new(self, arg):
    try:
        return mod(self, arg)
    except Exception:
        trans_log.error(unicode(self))
        return ''

Markup.__mod__ = new

import djcelery
djcelery.setup_loader()

# Import for side-effect: configures our logging handlers.
# pylint: disable-msg=W0611
from lib.utils import update_csp, validate_modules, validate_settings
update_csp()
validate_modules()
validate_settings()

import django.conf
newrelic_ini = getattr(django.conf.settings, 'NEWRELIC_INI', None)
load_newrelic = False

# Monkey patches DRF to not use fqdn urls.
from mkt.api.patch import patch
patch()

if newrelic_ini:
    import newrelic.agent
    try:
        newrelic.agent.initialize(newrelic_ini)
        load_newrelic = True
    except:
        startup_logger = logging.getLogger('z.startup')
        startup_logger.exception('Failed to load new relic config.')

# Alter zamboni to run on a particular port as per the
# marketplace docs, unless overridden.
from django.core.management.commands import runserver
runserver.DEFAULT_PORT = 2600

if __name__ == '__main__':
    execute_from_command_line(sys.argv)
