from django.db import connection, transaction

import cronjobs
import commonware.log

import amo


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
    p = ",".join(['%s'] * len(amo.VALID_STATUSES))
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
    """ % (p, p), amo.VALID_STATUSES * 2)
    transaction.commit_unless_managed()
