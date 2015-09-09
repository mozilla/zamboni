import datetime

from django.conf import settings

import mock
from nose.tools import eq_

import mkt
from mkt.abuse.models import AbuseReport
from mkt.developers.models import AppLog
from mkt.reviewers.models import EscalationQueue
from mkt.site.fixtures import fixture
from mkt.site.tests import app_factory, TestCase
from mkt.webapps.tasks import find_abuse_escalations


class TestAbuseEscalationTask(TestCase):
    fixtures = fixture('user_admin')

    def setUp(self):
        self.app = app_factory(name='XXX')
        eq_(EscalationQueue.objects.filter(addon=self.app).count(), 0)

        patcher = mock.patch.object(settings, 'TASK_USER_ID', 4043307)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_no_abuses_no_history(self):
        find_abuse_escalations(self.app.id)
        eq_(EscalationQueue.objects.filter(addon=self.app).count(), 0)

    def test_abuse_no_history(self):
        for x in range(2):
            AbuseReport.objects.create(addon=self.app)
        find_abuse_escalations(self.app.id)
        eq_(EscalationQueue.objects.filter(addon=self.app).count(), 1)

    def test_abuse_already_escalated(self):
        for x in range(2):
            AbuseReport.objects.create(addon=self.app)
        find_abuse_escalations(self.app.id)
        eq_(EscalationQueue.objects.filter(addon=self.app).count(), 1)
        find_abuse_escalations(self.app.id)
        eq_(EscalationQueue.objects.filter(addon=self.app).count(), 1)

    def test_abuse_cleared_not_escalated(self):
        for x in range(2):
            ar = AbuseReport.objects.create(addon=self.app)
            ar.created = datetime.datetime.now() - datetime.timedelta(days=1)
            ar.save()
        find_abuse_escalations(self.app.id)
        eq_(EscalationQueue.objects.filter(addon=self.app).count(), 1)

        # Simulate a reviewer clearing an escalation... remove app from queue,
        # and write a log.
        EscalationQueue.objects.filter(addon=self.app).delete()
        mkt.log(mkt.LOG.ESCALATION_CLEARED, self.app, self.app.current_version,
                details={'comments': 'All clear'})
        eq_(EscalationQueue.objects.filter(addon=self.app).count(), 0)

        # Task will find it again but not add it again.
        find_abuse_escalations(self.app.id)
        eq_(EscalationQueue.objects.filter(addon=self.app).count(), 0)

    def test_older_abuses_cleared_then_new(self):
        for x in range(2):
            ar = AbuseReport.objects.create(addon=self.app)
            ar.created = datetime.datetime.now() - datetime.timedelta(days=1)
            ar.save()
        find_abuse_escalations(self.app.id)
        eq_(EscalationQueue.objects.filter(addon=self.app).count(), 1)

        # Simulate a reviewer clearing an escalation... remove app from queue,
        # and write a log.
        EscalationQueue.objects.filter(addon=self.app).delete()
        mkt.log(mkt.LOG.ESCALATION_CLEARED, self.app, self.app.current_version,
                details={'comments': 'All clear'})
        eq_(EscalationQueue.objects.filter(addon=self.app).count(), 0)

        # Task will find it again but not add it again.
        find_abuse_escalations(self.app.id)
        eq_(EscalationQueue.objects.filter(addon=self.app).count(), 0)

        # New abuse reports that come in should re-add to queue.
        for x in range(2):
            AbuseReport.objects.create(addon=self.app)
        find_abuse_escalations(self.app.id)
        eq_(EscalationQueue.objects.filter(addon=self.app).count(), 1)

    def test_already_escalated_for_other_still_logs(self):
        # Add app to queue for high refunds.
        EscalationQueue.objects.create(addon=self.app)
        mkt.log(mkt.LOG.ESCALATED_HIGH_REFUNDS, self.app,
                self.app.current_version, details={'comments': 'hi refunds'})

        # Set up abuses.
        for x in range(2):
            AbuseReport.objects.create(addon=self.app)
        find_abuse_escalations(self.app.id)

        # Verify it logged the high abuse reports.
        action = mkt.LOG.ESCALATED_HIGH_ABUSE
        assert AppLog.objects.filter(
            addon=self.app, activity_log__action=action.id).exists(), (
                u'Expected high abuse to be logged')
