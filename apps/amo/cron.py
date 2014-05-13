from datetime import datetime, timedelta
from subprocess import Popen, PIPE

from django.conf import settings
from django.db import connection, transaction

import cronjobs
import commonware.log

import amo
from amo.utils import chunked
from bandwagon.models import Collection
from constants.base import VALID_STATUSES
from devhub.models import ActivityLog
from stats.models import Contribution

from . import tasks

log = commonware.log.getLogger('z.cron')


@cronjobs.register
def gc(test_result=True):
    """Site-wide garbage collections."""

    days_ago = lambda days: datetime.today() - timedelta(days=days)

    log.debug('Collecting data to delete')

    logs = (ActivityLog.objects.filter(created__lt=days_ago(90))
            .exclude(action__in=amo.LOG_KEEP).values_list('id', flat=True))

    # Paypal only keeps retrying to verify transactions for up to 3 days. If we
    # still have an unverified transaction after 6 days, we might as well get
    # rid of it.
    contributions_to_delete = (Contribution.objects
            .filter(transaction_id__isnull=True, created__lt=days_ago(6))
            .values_list('id', flat=True))

    collections_to_delete = (Collection.objects.filter(
            created__lt=days_ago(2), type=amo.COLLECTION_ANONYMOUS)
            .values_list('id', flat=True))

    for chunk in chunked(logs, 100):
        tasks.delete_logs.delay(chunk)
    for chunk in chunked(contributions_to_delete, 100):
        tasks.delete_stale_contributions.delay(chunk)
    for chunk in chunked(collections_to_delete, 100):
        tasks.delete_anonymous_collections.delay(chunk)
    # Incomplete addons cannot be deleted here because when an addon is
    # rejected during a review it is marked as incomplete. See bug 670295.

    log.debug('Cleaning up test results extraction cache.')
    # lol at check for '/'
    if settings.NETAPP_STORAGE and settings.NETAPP_STORAGE != '/':
        cmd = ('find', settings.NETAPP_STORAGE, '-maxdepth', '1', '-name',
               'validate-*', '-mtime', '+7', '-type', 'd',
               '-exec', 'rm', '-rf', "{}", ';')

        output = Popen(cmd, stdout=PIPE).communicate()[0]

        for line in output.split("\n"):
            log.debug(line)

    else:
        log.warning('NETAPP_STORAGE not defined.')

    if settings.COLLECTIONS_ICON_PATH:
        log.debug('Cleaning up uncompressed icons.')

        cmd = ('find', settings.COLLECTIONS_ICON_PATH,
               '-name', '*__unconverted', '-mtime', '+1', '-type', 'f',
               '-exec', 'rm', '{}', ';')
        output = Popen(cmd, stdout=PIPE).communicate()[0]

        for line in output.split("\n"):
            log.debug(line)

    if settings.USERPICS_PATH:
        log.debug('Cleaning up uncompressed userpics.')

        cmd = ('find', settings.USERPICS_PATH,
               '-name', '*__unconverted', '-mtime', '+1', '-type', 'f',
               '-exec', 'rm', '{}', ';')
        output = Popen(cmd, stdout=PIPE).communicate()[0]

        for line in output.split("\n"):
            log.debug(line)


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
def collection_subscribers():
    """
    Collection weekly and monthly subscriber counts.
    """
    log.debug('Starting collection subscriber update...')
    cursor = connection.cursor()
    cursor.execute("""
        UPDATE collections SET weekly_subscribers = 0, monthly_subscribers = 0
    """)
    cursor.execute("""
        UPDATE collections AS c
        INNER JOIN (
            SELECT
                COUNT(collection_id) AS count,
                collection_id
            FROM collection_subscriptions
            WHERE created >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
            GROUP BY collection_id
        ) AS weekly ON (c.id = weekly.collection_id)
        INNER JOIN (
            SELECT
                COUNT(collection_id) AS count,
                collection_id
            FROM collection_subscriptions
            WHERE created >= DATE_SUB(CURDATE(), INTERVAL 31 DAY)
            GROUP BY collection_id
        ) AS monthly ON (c.id = monthly.collection_id)
        SET c.weekly_subscribers = weekly.count,
            c.monthly_subscribers = monthly.count
    """)
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
