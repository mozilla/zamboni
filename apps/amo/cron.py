from datetime import datetime, timedelta
from subprocess import Popen, PIPE

from django.conf import settings
from django.db import connection, transaction

import cronjobs
import commonware.log

import amo
from amo.utils import chunked
from constants.base import VALID_STATUSES
from devhub.models import ActivityLog
from stats.models import Contribution

from . import tasks

log = commonware.log.getLogger('z.cron')

@cronjobs.register
def expired_resetcode():
    """
    Delete password reset codes that have expired.
    """
    log.debug('Removing reset codes that have expired...')
    cursor = connection.cursor()
    cursor.execute("""
    UPDATE users SET resetcode=DEFAULT,
                     resetcode_expires=DEFAULT
    WHERE resetcode_expires < NOW()
    """)
    transaction.commit_unless_managed()


@cronjobs.register
def category_totals():
    """
    Update category counts for sidebar navigation.
    """
    log.debug('Starting category counts update...')
    p = ",".join(['%s'] * len(VALID_STATUSES))
    cursor = connection.cursor()
    cursor.execute("""
    UPDATE categories AS t INNER JOIN (
     SELECT at.category_id, COUNT(DISTINCT Addon.id) AS ct
      FROM addons AS Addon
      INNER JOIN versions AS Version ON (Addon.id = Version.addon_id)
      INNER JOIN applications_versions AS av ON (av.version_id = Version.id)
      INNER JOIN addons_categories AS at ON (at.addon_id = Addon.id)
      INNER JOIN files AS File ON (Version.id = File.version_id
                                   AND File.status IN (%s))
      WHERE Addon.status IN (%s) AND Addon.inactive = 0
      GROUP BY at.category_id)
    AS j ON (t.id = j.category_id)
    SET t.count = j.ct
    """ % (p, p), VALID_STATUSES * 2)
    transaction.commit_unless_managed()


@cronjobs.register
def unconfirmed():
    """
    Delete user accounts that have not been confirmed for two weeks.
    """
    log.debug("Removing user accounts that haven't been confirmed "
              "for two weeks...")
    cursor = connection.cursor()
    cursor.execute("""
        DELETE users
        FROM users
        LEFT JOIN addons_users on users.id = addons_users.user_id
        LEFT JOIN addons_collections ON users.id=addons_collections.user_id
        LEFT JOIN collections_users ON users.id=collections_users.user_id
        WHERE users.created < DATE_SUB(CURDATE(), INTERVAL 2 WEEK)
        AND users.confirmationcode != ''
        AND addons_users.user_id IS NULL
        AND addons_collections.user_id IS NULL
        AND collections_users.user_id IS NULL
    """)
    transaction.commit_unless_managed()
