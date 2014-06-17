import datetime

from django.core.mail import EmailMessage, EmailMultiAlternatives

import commonware.log
from celeryutils import task

import amo
from amo.decorators import set_task_user
from amo.utils import get_email_backend
from mkt.abuse.models import AbuseReport
from mkt.developers.models import ActivityLog, AppLog
from mkt.prices.models import Refund
from mkt.reviewers.models import EscalationQueue
from mkt.webapps.models import Addon


log = commonware.log.getLogger('z.task')


@task
def send_email(recipient, subject, message, from_email=None,
               html_message=None, attachments=None, real_email=False,
               cc=None, headers=None, fail_silently=False, async=False,
               max_retries=None, **kwargs):
    backend = EmailMultiAlternatives if html_message else EmailMessage
    connection = get_email_backend(real_email)
    result = backend(subject, message,
                     from_email, recipient, cc=cc, connection=connection,
                     headers=headers, attachments=attachments)
    if html_message:
        result.attach_alternative(html_message, 'text/html')
    try:
        result.send(fail_silently=False)
        return True
    except Exception as e:
        log.error('send_mail failed with error: %s' % e)
        if async:
            return send_email.retry(exc=e, max_retries=max_retries)
        elif not fail_silently:
            raise
        else:
            return False


@task
def set_modified_on_object(obj, **kw):
    """Sets modified on one object at a time."""
    try:
        log.info('Setting modified on object: %s, %s' %
                 (obj.__class__.__name__, obj.pk))
        obj.update(modified=datetime.datetime.now(), **kw)
    except Exception, e:
        log.error('Failed to set modified on: %s, %s - %s' %
                  (obj.__class__.__name__, obj.pk, e))


@task
def delete_logs(items, **kw):
    log.info('[%s@%s] Deleting logs' % (len(items), delete_logs.rate_limit))
    ActivityLog.objects.filter(pk__in=items).exclude(
        action__in=amo.LOG_KEEP).delete()


@task
@set_task_user
def find_abuse_escalations(addon_id, **kw):
    weekago = datetime.date.today() - datetime.timedelta(days=7)
    add_to_queue = True

    for abuse in AbuseReport.recent_high_abuse_reports(1, weekago, addon_id):
        if EscalationQueue.objects.filter(addon=abuse.addon).exists():
            # App is already in the queue, no need to re-add it.
            log.info(u'[addon:%s] High abuse reports, but already escalated' %
                     (abuse.addon,))
            add_to_queue = False

        # We have an abuse report... has it been detected and dealt with?
        logs = (AppLog.objects.filter(
            activity_log__action=amo.LOG.ESCALATED_HIGH_ABUSE.id,
            addon=abuse.addon).order_by('-created'))
        if logs:
            abuse_since_log = AbuseReport.recent_high_abuse_reports(
                1, logs[0].created, addon_id)
            # If no abuse reports have happened since the last logged abuse
            # report, do not add to queue.
            if not abuse_since_log:
                log.info(u'[addon:%s] High abuse reports, but none since last '
                         u'escalation' % abuse.addon)
                continue

        # If we haven't bailed out yet, escalate this app.
        msg = u'High number of abuse reports detected'
        if add_to_queue:
            EscalationQueue.objects.create(addon=abuse.addon)
        amo.log(amo.LOG.ESCALATED_HIGH_ABUSE, abuse.addon,
                abuse.addon.current_version, details={'comments': msg})
        log.info(u'[addon:%s] %s' % (abuse.addon, msg))


@task
@set_task_user
def find_refund_escalations(addon_id, **kw):
    try:
        addon = Addon.objects.get(pk=addon_id)
    except Addon.DoesNotExist:
        log.info(u'[addon:%s] Task called but no addon found.' % addon_id)
        return

    refund_threshold = 0.05
    weekago = datetime.date.today() - datetime.timedelta(days=7)
    add_to_queue = True

    ratio = Refund.recent_refund_ratio(addon.id, weekago)
    if ratio > refund_threshold:
        if EscalationQueue.objects.filter(addon=addon).exists():
            # App is already in the queue, no need to re-add it.
            log.info(u'[addon:%s] High refunds, but already escalated' % addon)
            add_to_queue = False

        # High refunds... has it been detected and dealt with already?
        logs = (AppLog.objects.filter(
            activity_log__action=amo.LOG.ESCALATED_HIGH_REFUNDS.id,
            addon=addon).order_by('-created', '-id'))
        if logs:
            since_ratio = Refund.recent_refund_ratio(addon.id, logs[0].created)
            # If not high enough ratio since the last logged, do not add to
            # the queue.
            if not since_ratio > refund_threshold:
                log.info(u'[addon:%s] High refunds, but not enough since last '
                         u'escalation. Ratio: %.0f%%' % (addon,
                                                         since_ratio * 100))
                return

        # If we haven't bailed out yet, escalate this app.
        msg = u'High number of refund requests (%.0f%%) detected.' % (
            (ratio * 100),)
        if add_to_queue:
            EscalationQueue.objects.create(addon=addon)
        amo.log(amo.LOG.ESCALATED_HIGH_REFUNDS, addon,
                addon.current_version, details={'comments': msg})
        log.info(u'[addon:%s] %s' % (addon, msg))
