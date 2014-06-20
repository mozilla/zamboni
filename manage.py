#!/usr/bin/env python
import logging
import os
import site
import sys

from django.core.management import call_command, execute_from_command_line


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mkt.settings')

ROOT = os.path.dirname(os.path.abspath(__file__))
path = lambda *a: os.path.join(ROOT, *a)

site.addsitedir(path('apps'))

import session_csrf
session_csrf.monkeypatch()

# Fix jinja's Markup class to not crash when localizers give us bad format
# strings.
from jinja2 import Markup
mod = Markup.__mod__
trans_log = logging.getLogger('z.trans')


# waffle and amo form an import cycle because amo patches waffle and
# waffle loads the user model, so we have to make sure amo gets
# imported before anything else imports waffle.
import amo

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
from lib.utils import validate_settings
from lib.log_settings_base import log_configure
log_configure()
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

if __name__ == "__main__":
    # If product details aren't present, get them.
    from product_details import product_details
    if not product_details.last_update:
        print 'Product details missing, downloading...'
        call_command('update_product_details')
        product_details.__init__()  # reload the product details

    execute_from_command_line(sys.argv)
