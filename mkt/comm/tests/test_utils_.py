from django.core.files.uploadedfile import SimpleUploadedFile

import mock
from nose.tools import eq_

from mkt.comm.forms import CommAttachmentFormSet
from mkt.comm.tests.test_views import AttachmentManagementMixin
from mkt.comm.utils import create_comm_note
from mkt.constants import comm
from mkt.site.tests import TestCase, user_factory
from mkt.site.utils import app_factory, extension_factory


class TestCreateCommNote(TestCase, AttachmentManagementMixin):

    def setUp(self):
        self.contact = user_factory(email='contact')
        self.user = user_factory()
        self.grant_permission(self.user, '*:*')
        self.app = app_factory(mozilla_contact=self.contact.email)

    def test_create_thread(self):
        # Default permissions.
        thread, note = create_comm_note(
            self.app, self.app.current_version, self.user, 'huehue',
            note_type=comm.APPROVAL)

        # Check Thread.
        eq_(thread.addon, self.app)
        eq_(thread.version, self.app.current_version)
        expected = {
            'public': False, 'developer': True, 'reviewer': True,
            'senior_reviewer': True, 'mozilla_contact': True, 'staff': True}
        for perm, has_perm in expected.items():
            eq_(getattr(thread, 'read_permission_%s' % perm), has_perm, perm)

        # Check Note.
        eq_(note.thread, thread)
        eq_(note.author, self.user)
        eq_(note.body, 'huehue')
        eq_(note.note_type, comm.APPROVAL)

        # Check CC.
        eq_(thread.thread_cc.count(), 2)
        assert thread.thread_cc.filter(user=self.contact).exists()
        assert thread.thread_cc.filter(user=self.user).exists()

    def test_create_note_existing_thread(self):
        # Initial note.
        thread, note = create_comm_note(
            self.app, self.app.current_version, self.user, 'huehue')

        # Second note from contact.
        thread, reply = create_comm_note(
            self.app, self.app.current_version, self.contact, 'euheuh!',
            note_type=comm.REJECTION)

        # Third person joins thread.
        thread, last_word = create_comm_note(
            self.app, self.app.current_version, user_factory(), 'euheuh!',
            note_type=comm.MORE_INFO_REQUIRED)

        eq_(thread.thread_cc.count(), 3)

    def test_create_note_no_author(self):
        thread, note = create_comm_note(
            self.app, self.app.current_version, None, 'huehue')
        eq_(note.author, None)

    @mock.patch('mkt.comm.utils.post_create_comm_note', new=mock.Mock)
    def test_create_note_reviewer_type(self):
        for note_type in comm.REVIEWER_NOTE_TYPES:
            thread, note = create_comm_note(
                self.app, self.app.current_version, None, 'huehue',
                note_type=note_type)
            eq_(note.read_permission_developer, False)

    @mock.patch('mkt.comm.utils.post_create_comm_note', new=mock.Mock)
    def test_custom_perms(self):
        thread, note = create_comm_note(
            self.app, self.app.current_version, self.user, 'escalatedquickly',
            note_type=comm.ESCALATION, perms={'developer': False,
                                              'staff': True})

        expected = {
            'public': False, 'developer': False, 'reviewer': True,
            'senior_reviewer': True, 'mozilla_contact': True, 'staff': True}
        for perm, has_perm in expected.items():
            eq_(getattr(thread, 'read_permission_%s' % perm), has_perm, perm)

    @mock.patch('mkt.comm.utils.post_create_comm_note', new=mock.Mock)
    def test_attachments(self):
        attach_formdata = self._attachment_management_form(num=2)
        attach_formdata.update(self._attachments(num=2))
        attach_formset = CommAttachmentFormSet(
            attach_formdata,
            {'form-0-attachment':
                SimpleUploadedFile(
                    'lol', attach_formdata['form-0-attachment'].read()),
             'form-1-attachment':
                SimpleUploadedFile(
                    'lol2', attach_formdata['form-1-attachment'].read())})

        thread, note = create_comm_note(
            self.app, self.app.current_version, self.user, 'lol',
            note_type=comm.APPROVAL, attachments=attach_formset)

        eq_(note.attachments.count(), 2)


class TestCreateCommNoteExtensions(TestCase, AttachmentManagementMixin):

    def setUp(self):
        self.user = user_factory()
        self.grant_permission(self.user, '*:*')
        self.extension = extension_factory()

    def test_create_thread(self):
        # Default permissions.
        thread, note = create_comm_note(
            self.extension, self.extension.latest_version, self.user, 'huehue',
            note_type=comm.APPROVAL)

        # Check Thread.
        eq_(thread.obj, self.extension)
        eq_(thread._extension, self.extension)
        eq_(thread.version, self.extension.latest_version)
        eq_(thread._extension_version, self.extension.latest_version)

        expected = {
            'public': False, 'developer': True, 'reviewer': True,
            'senior_reviewer': True, 'mozilla_contact': True, 'staff': True}
        for perm, has_perm in expected.items():
            eq_(getattr(thread, 'read_permission_%s' % perm), has_perm, perm)

        # Check Note.
        eq_(note.thread, thread)
        eq_(note.author, self.user)
        eq_(note.body, 'huehue')
        eq_(note.note_type, comm.APPROVAL)

        # Check CC.
        eq_(thread.thread_cc.count(), 1)
        assert thread.thread_cc.filter(user=self.user).exists()

    def test_create_note_existing_thread(self):
        # Initial note.
        thread, note = create_comm_note(
            self.extension, self.extension.latest_version, self.user, 'huehue')

        # Second person joins thread.
        thread, last_word = create_comm_note(
            self.extension, self.extension.latest_version, user_factory(),
            'euheuh!', note_type=comm.MORE_INFO_REQUIRED)

        eq_(thread.thread_cc.count(), 2)

    def test_create_note_no_author(self):
        thread, note = create_comm_note(
            self.extension, self.extension.latest_version, None, 'huehue')
        eq_(note.author, None)

    @mock.patch('mkt.comm.utils.post_create_comm_note', new=mock.Mock)
    def test_create_note_reviewer_type(self):
        for note_type in comm.REVIEWER_NOTE_TYPES:
            thread, note = create_comm_note(
                self.extension, self.extension.latest_version, None, 'huehue',
                note_type=note_type)
            eq_(note.read_permission_developer, False)

    @mock.patch('mkt.comm.utils.post_create_comm_note', new=mock.Mock)
    def test_custom_perms(self):
        thread, note = create_comm_note(
            self.extension, self.extension.latest_version, self.user,
            'escalatedquickly', note_type=comm.ESCALATION,
            perms={'developer': False, 'staff': True})

        expected = {
            'public': False, 'developer': False, 'reviewer': True,
            'senior_reviewer': True, 'mozilla_contact': True, 'staff': True}
        for perm, has_perm in expected.items():
            eq_(getattr(thread, 'read_permission_%s' % perm), has_perm, perm)

    @mock.patch('mkt.comm.utils.post_create_comm_note', new=mock.Mock)
    def test_attachments(self):
        attach_formdata = self._attachment_management_form(num=2)
        attach_formdata.update(self._attachments(num=2))
        attach_formset = CommAttachmentFormSet(
            attach_formdata,
            {'form-0-attachment':
                SimpleUploadedFile(
                    'lol', attach_formdata['form-0-attachment'].read()),
             'form-1-attachment':
                SimpleUploadedFile(
                    'lol2', attach_formdata['form-1-attachment'].read())})

        thread, note = create_comm_note(
            self.extension, self.extension.latest_version, self.user, 'lol',
            note_type=comm.APPROVAL, attachments=attach_formset)

        eq_(note.attachments.count(), 2)
