from django.core.management import call_command

from nose.tools import eq_, ok_

import mkt
from mkt.comm.models import CommunicationNote, CommunicationThread
from mkt.constants import comm
from mkt.developers.models import ActivityLog, ActivityLogAttachment
from mkt.site.fixtures import fixture
from mkt.site.tests import TestCase, user_factory
from mkt.site.utils import app_factory
from mkt.users.models import UserProfile


class TestMigrateActivityLog(TestCase):
    fixtures = fixture('group_editor', 'user_editor', 'user_editor_group')

    def setUp(self):
        self.app = app_factory(status=mkt.STATUS_PENDING)
        self.version = self.app.latest_version
        self.user = UserProfile.objects.get()

    def _assert(self, comm_action):
        call_command('migrate_activity_log')
        thread = CommunicationThread.objects.get()
        note = CommunicationNote.objects.get()

        eq_(thread.addon, self.app)
        eq_(thread.version, self.version)

        eq_(note.thread, thread)
        eq_(note.author, self.user)
        eq_(note.body, 'something')
        eq_(note.note_type, comm_action)

        eq_(note.read_permission_staff, True)
        eq_(note.read_permission_reviewer, True)
        eq_(note.read_permission_senior_reviewer, True)
        eq_(note.read_permission_mozilla_contact, True)

        return thread, note

    def test_migrate(self):
        mkt.log(mkt.LOG.APPROVE_VERSION, self.app, self.version,
                user=self.user, details={'comments': 'something'})
        self._assert(comm.APPROVAL)

    def test_migrate_reject(self):
        mkt.log(mkt.LOG.REJECT_VERSION, self.app, self.version,
                user=self.user, details={'comments': 'something'})
        self._assert(comm.REJECTION)

    def test_migrate_disable(self):
        mkt.log(mkt.LOG.APP_DISABLED, self.app, self.version,
                user=self.user, details={'comments': 'something'})
        self._assert(comm.DISABLED)

    def test_migrate_escalation(self):
        mkt.log(mkt.LOG.ESCALATE_VERSION, self.app, self.version,
                user=self.user, details={'comments': 'something'})
        thread, note = self._assert(comm.ESCALATION)
        assert not note.read_permission_developer

    def test_migrate_reviewer_comment(self):
        mkt.log(mkt.LOG.COMMENT_VERSION, self.app, self.version,
                user=self.user, details={'comments': 'something'})
        thread, note = self._assert(comm.REVIEWER_COMMENT)
        assert not note.read_permission_developer

    def test_migrate_info(self):
        mkt.log(mkt.LOG.REQUEST_INFORMATION, self.app, self.version,
                user=self.user, details={'comments': 'something'})
        self._assert(comm.MORE_INFO_REQUIRED)

    def test_migrate_noaction(self):
        mkt.log(mkt.LOG.REQUEST_VERSION, self.app, self.version,
                user=self.user, details={'comments': 'something'})
        self._assert(comm.NO_ACTION)

    def test_migrate_escalation_high_abuse(self):
        mkt.log(mkt.LOG.ESCALATED_HIGH_ABUSE, self.app, self.version,
                user=self.user, details={'comments': 'something'})
        thread, note = self._assert(comm.ESCALATION_HIGH_ABUSE)
        assert not note.read_permission_developer

    def test_migrate_escalation_high_refunds(self):
        mkt.log(mkt.LOG.ESCALATED_HIGH_REFUNDS, self.app, self.version,
                user=self.user, details={'comments': 'something'})
        thread, note = self._assert(comm.ESCALATION_HIGH_REFUNDS)
        assert not note.read_permission_developer

    def test_migrate_escalation_cleared(self):
        mkt.log(mkt.LOG.ESCALATION_CLEARED, self.app, self.version,
                user=self.user, details={'comments': 'something'})
        thread, note = self._assert(comm.ESCALATION_CLEARED)
        assert not note.read_permission_developer

    def test_get_or_create(self):
        mkt.log(mkt.LOG.REQUEST_VERSION, self.app, self.version,
                user=self.user, details={'comments': 'something'})
        self._assert(comm.NO_ACTION)
        call_command('migrate_activity_log')
        call_command('migrate_activity_log')
        eq_(CommunicationNote.objects.count(), 1)

        mkt.log(mkt.LOG.REQUEST_VERSION, self.app, self.version,
                user=self.user, details={'comments': 'somethingNEW'})
        call_command('migrate_activity_log')
        eq_(CommunicationNote.objects.count(), 2)

        eq_(CommunicationThread.objects.count(), 1)

    def test_empty_comment(self):
        mkt.log(mkt.LOG.REQUEST_VERSION, self.app, self.version,
                user=self.user, details={})
        call_command('migrate_activity_log')
        note = CommunicationNote.objects.get()
        eq_(note.thread.addon, self.app)
        eq_(note.body, '')

    def test_none(self):
        call_command('migrate_activity_log')
        assert not CommunicationThread.objects.exists()
        assert not CommunicationNote.objects.exists()

    def test_migrate_attachments(self):
        mkt.log(mkt.LOG.APPROVE_VERSION, self.app, self.version,
                user=self.user, details={'comments': 'something'})
        ActivityLogAttachment.objects.create(
            activity_log=ActivityLog.objects.get(), filepath='lol',
            description='desc1', mimetype='img')
        ActivityLogAttachment.objects.create(
            activity_log=ActivityLog.objects.get(), filepath='rofl',
            description='desc2', mimetype='txt')
        call_command('migrate_activity_log')

        note = CommunicationNote.objects.get()
        eq_(note.attachments.count(), 2)

        note_attach1 = note.attachments.get(filepath='lol')
        eq_(note_attach1.description, 'desc1')
        eq_(note_attach1.mimetype, 'img')
        note_attach2 = note.attachments.get(filepath='rofl')
        eq_(note_attach2.description, 'desc2')
        eq_(note_attach2.mimetype, 'txt')


class TestMigrateApprovalNotes(TestCase):

    def setUp(self):
        self.app = app_factory()
        self.version = self.app.latest_version
        self.thread = CommunicationThread.objects.create(
            _addon=self.app, _version=self.version)
        self.user = user_factory()
        self.app.addonuser_set.create(user=self.user)

    def test_basic_migrate(self):
        self.version.update(approvalnotes='susurrus')
        call_command('migrate_approval_notes')
        eq_(self.thread.notes.all()[0].body, 'susurrus')
        eq_(self.thread.notes.all()[0].note_type,
            comm.DEVELOPER_VERSION_NOTE_FOR_REVIEWER)
        eq_(self.thread.notes.all()[0].author, self.user)

    def test_exists(self):
        self.version.update(approvalnotes='geringdingding')
        self.thread.notes.create(
            body='no touching',
            note_type=comm.DEVELOPER_VERSION_NOTE_FOR_REVIEWER)
        call_command('migrate_approval_notes')
        eq_(self.thread.notes.all()[0].body, 'no touching')
        eq_(self.thread.notes.all()[0].note_type,
            comm.DEVELOPER_VERSION_NOTE_FOR_REVIEWER)

    def test_no_thread(self):
        self.thread.delete()
        call_command('migrate_approval_notes')


class TestFixDeveloperVersionNotes(TestCase):

    def setUp(self):
        self.app = app_factory(status=mkt.STATUS_PENDING)
        self.version = self.app.latest_version
        self.thread = CommunicationThread.objects.create(
            _addon=self.app, _version=self.version)
        self.user = user_factory()
        self.app.addonuser_set.create(user=self.user)

    def test_basic_fix(self):
        self.thread.notes.create(note_type=comm.REVIEWER_COMMENT,
                                 author=self.user)
        call_command('fix_developer_version_notes')
        eq_(self.thread.notes.all()[0].note_type,
            comm.DEVELOPER_VERSION_NOTE_FOR_REVIEWER)

    def test_not_developer(self):
        self.app.addonuser_set.all().delete()
        self.thread.notes.create(note_type=comm.REVIEWER_COMMENT,
                                 author=self.user)
        call_command('fix_developer_version_notes')
        eq_(self.thread.notes.all()[0].note_type,
            comm.REVIEWER_COMMENT)

    def test_not_first_or_second_note(self):
        first_note = self.thread.notes.create(note_type=comm.SUBMISSION,
                                              author=self.user)
        first_note.update(created=self.days_ago(123))
        second_note = self.thread.notes.create(note_type=comm.SUBMISSION,
                                               author=self.user)
        second_note.update(created=self.days_ago(123))
        self.thread.notes.create(note_type=comm.REVIEWER_COMMENT,
                                 author=self.user)
        call_command('fix_developer_version_notes')
        ok_(self.thread.notes.filter(note_type=comm.REVIEWER_COMMENT).exists())

    def test_not_reviewer_comment(self):
        self.thread.notes.create(note_type=comm.SUBMISSION, author=self.user)
        call_command('fix_developer_version_notes')
        ok_(self.thread.notes.filter(note_type=comm.SUBMISSION).exists())

    def test_deleted_app(self):
        self.thread.notes.create(note_type=comm.REVIEWER_COMMENT,
                                 author=self.user)
        self.thread.addon.delete()
        call_command('fix_developer_version_notes')
        eq_(self.thread.notes.all()[0].note_type,
            comm.DEVELOPER_VERSION_NOTE_FOR_REVIEWER)
