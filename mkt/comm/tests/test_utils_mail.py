import base64
import os.path

from django.conf import settings
from django.core import mail

import mock
from nose import SkipTest
from nose.tools import eq_, ok_

import mkt
from mkt.comm.models import CommunicationThread, CommunicationThreadToken
from mkt.comm.tests.test_views import CommTestMixin
from mkt.comm.utils import create_comm_note
from mkt.comm.utils_mail import (CommEmailParser, get_mail_context,
                                 save_from_email_reply)
from mkt.constants import comm
from mkt.site.fixtures import fixture
from mkt.site.tests import TestCase, user_factory
from mkt.site.utils import app_factory, extension_factory
from mkt.users.models import UserProfile


sample_email = os.path.join(settings.ROOT, 'mkt', 'comm', 'tests', 'emails',
                            'email.txt')
multi_email = os.path.join(settings.ROOT, 'mkt', 'comm', 'tests', 'emails',
                           'email_multipart.txt')
quopri_email = os.path.join(settings.ROOT, 'mkt', 'comm', 'tests', 'emails',
                            'email_quoted_printable.txt')
attach_email = os.path.join(settings.ROOT, 'mkt', 'comm', 'tests', 'emails',
                            'email_attachment.txt')
attach_email2 = os.path.join(settings.ROOT, 'mkt', 'comm', 'tests', 'emails',
                             'email_attachment2.txt')


class TestSendMailComm(TestCase, CommTestMixin):

    def setUp(self):
        self.developer = user_factory()
        self.mozilla_contact = user_factory()
        self.reviewer = user_factory()
        self.senior_reviewer = user_factory()

        self.grant_permission(self.senior_reviewer, '*:*',
                              'Senior App Reviewers')

        self.app = app_factory()
        self.app.addonuser_set.create(user=self.developer)
        self.app.update(mozilla_contact=self.mozilla_contact.email)

    def _create(self, note_type, author=None):
        author = author or self.reviewer
        return create_comm_note(self.app, self.app.current_version, author,
                                'Test Comment', note_type=note_type)

    def _recipients(self, email_mock):
        recipients = []
        for call in email_mock.call_args_list:
            recipients += call[1]['recipient_list']
        return recipients

    def _check_template(self, call, template):
        eq_(call[0][1], 'comm/emails/%s.html' % template)

    @mock.patch('mkt.comm.utils_mail.send_mail_jinja')
    def test_approval(self, email):
        self._create(comm.APPROVAL)
        eq_(email.call_count, 2)

        recipients = self._recipients(email)
        assert self.developer.email in recipients
        assert self.mozilla_contact.email in recipients

        self._check_template(email.call_args, 'approval')

    @mock.patch('mkt.comm.utils_mail.send_mail_jinja')
    def test_rejection(self, email):
        self._create(comm.REJECTION)
        eq_(email.call_count, 2)

        recipients = self._recipients(email)
        assert self.developer.email in recipients
        assert self.mozilla_contact.email in recipients

        self._check_template(email.call_args, 'rejection')

    @mock.patch('mkt.comm.utils_mail.send_mail_jinja')
    def test_escalation(self, email):
        self._create(comm.ESCALATION)
        eq_(email.call_count, 2)

        recipients = self._recipients(email)
        assert self.developer.email in recipients
        assert self.senior_reviewer.email in recipients

        self._check_template(email.call_args_list[0],
                             'escalation_senior_reviewer')
        self._check_template(email.call_args_list[1],
                             'escalation_developer')

    @mock.patch('mkt.comm.utils_mail.send_mail_jinja')
    def test_escalation_vip_app(self, email):
        self._create(comm.ESCALATION_VIP_APP)
        eq_(email.call_count, 1)

        recipients = self._recipients(email)
        assert self.senior_reviewer.email in recipients

        self._check_template(email.call_args,
                             'escalation_vip')

    @mock.patch('mkt.comm.utils_mail.send_mail_jinja')
    def test_escalation_prerelease_app(self, email):
        self._create(comm.ESCALATION_PRERELEASE_APP)
        eq_(email.call_count, 1)

        recipients = self._recipients(email)
        assert self.senior_reviewer.email in recipients

        self._check_template(email.call_args,
                             'escalation_prerelease_app')

    @mock.patch('mkt.comm.utils_mail.send_mail_jinja')
    def test_reviewer_comment(self, email):
        another_reviewer = user_factory()
        self._create(comm.REVIEWER_COMMENT, author=self.reviewer)
        self._create(comm.REVIEWER_COMMENT, author=another_reviewer)
        eq_(email.call_count, 3)

        recipients = self._recipients(email)
        assert self.reviewer.email in recipients
        assert self.mozilla_contact.email in recipients
        assert self.developer.email not in recipients

        self._check_template(email.call_args, 'generic')

    @mock.patch('mkt.comm.utils_mail.send_mail_jinja')
    def test_developer_comment(self, email):
        self._create(comm.REVIEWER_COMMENT)
        self._create(comm.DEVELOPER_COMMENT, author=self.developer)
        eq_(email.call_count, 4)

        recipients = self._recipients(email)
        assert self.mozilla_contact.email in recipients
        assert self.reviewer.email in recipients
        assert self.developer.email not in recipients
        assert settings.MKT_REVIEWS_EMAIL in recipients

        self._check_template(email.call_args, 'generic')

    @mock.patch('mkt.comm.utils_mail.send_mail_jinja')
    def test_additional_review(self, email):
        self._create(comm.ADDITIONAL_REVIEW_PASSED)
        eq_(email.call_count, 2)

        recipients = self._recipients(email)
        assert self.mozilla_contact.email in recipients
        assert self.developer.email in recipients

        self._check_template(email.call_args, 'tarako')

    def test_mail_templates_exist(self):
        for note_type in comm.COMM_MAIL_MAP:
            self._create(note_type)
        for note_type in comm.EMAIL_SENIOR_REVIEWERS_AND_DEV:
            self._create(note_type)
        self._create(comm.NO_ACTION)

    def test_email_formatting(self):
        """
        Manually run test in case you want to spot-check if every email is
        formatted nicely and consistently. Prints out each note type email
        once.
        """
        raise SkipTest
        for note_type in comm.COMM_MAIL_MAP:
            self._create(note_type)

        email_subjects = []
        for email in mail.outbox:
            if email.subject in email_subjects:
                continue
            email_subjects.append(email_subjects)

            print '##### %s #####' % email.subject
            print email.body

    @mock.patch('mkt.comm.utils_mail.send_mail_jinja')
    def test_reply_to(self, email):
        note, thread = self._create(comm.APPROVAL)
        reply_to = email.call_args_list[1][1]['headers']['Reply-To']
        ok_(reply_to.startswith('commreply+'))
        ok_(reply_to.endswith('marketplace.firefox.com'))


class TestSendMailCommExtensions(TestCase, CommTestMixin):

    def setUp(self):
        self.developer = user_factory()
        self.reviewer = user_factory()

        self.extension = extension_factory()
        self.developer.extension_set.add(self.extension)

    def _create(self, note_type, author=None):
        author = author or self.reviewer
        return create_comm_note(
            self.extension, self.extension.latest_version, author,
            'Test Comment', note_type=note_type)

    def _recipients(self, email_mock):
        recipients = []
        for call in email_mock.call_args_list:
            recipients += call[1]['recipient_list']
        return recipients

    def _check_template(self, call, template):
        eq_(call[0][1], 'comm/emails/%s.html' % template)

    @mock.patch('mkt.comm.utils_mail.send_mail_jinja')
    def test_approval(self, email):
        self._create(comm.APPROVAL)
        eq_(email.call_count, 1)

        recipients = self._recipients(email)
        assert self.developer.email in recipients

        self._check_template(email.call_args, 'approval')

    @mock.patch('mkt.comm.utils_mail.send_mail_jinja')
    def test_rejection(self, email):
        self._create(comm.REJECTION)
        eq_(email.call_count, 1)

        recipients = self._recipients(email)
        assert self.developer.email in recipients

        self._check_template(email.call_args, 'rejection')

    @mock.patch('mkt.comm.utils_mail.send_mail_jinja')
    def test_reviewer_comment(self, email):
        another_reviewer = user_factory()
        self._create(comm.REVIEWER_COMMENT, author=self.reviewer)
        self._create(comm.REVIEWER_COMMENT, author=another_reviewer)
        eq_(email.call_count, 1)

        recipients = self._recipients(email)
        assert self.reviewer.email in recipients
        assert self.developer.email not in recipients

        self._check_template(email.call_args, 'generic')

    @mock.patch('mkt.comm.utils_mail.send_mail_jinja')
    def test_developer_comment(self, email):
        self._create(comm.REVIEWER_COMMENT)
        self._create(comm.DEVELOPER_COMMENT, author=self.developer)
        eq_(email.call_count, 2)

        recipients = self._recipients(email)
        assert self.reviewer.email in recipients
        assert settings.MKT_REVIEWS_EMAIL in recipients
        assert self.developer.email not in recipients

        self._check_template(email.call_args, 'generic')

    @mock.patch('mkt.comm.utils_mail.send_mail_jinja')
    def test_reply_to(self, email):
        note, thread = self._create(comm.APPROVAL)
        reply_to = email.call_args_list[0][1]['headers']['Reply-To']
        ok_(reply_to.startswith('commreply+'))
        ok_(reply_to.endswith('marketplace.firefox.com'))


class TestEmailReplySaving(TestCase):
    fixtures = fixture('user_999')

    def setUp(self):
        self.app = app_factory(name='Antelope', status=mkt.STATUS_PENDING)
        self.profile = UserProfile.objects.get(pk=999)
        t = CommunicationThread.objects.create(
            _addon=self.app, _version=self.app.current_version,
            read_permission_reviewer=True)

        self.token = CommunicationThreadToken.objects.create(
            thread=t, user=self.profile)
        self.token.update(uuid='5a0b8a83d501412589cc5d562334b46b')
        self.email_base64 = open(sample_email).read()
        self.grant_permission(self.profile, 'Apps:Review')

    def test_successful_save(self):
        note = save_from_email_reply(self.email_base64)
        eq_(note.body, 'test note 5\n')

    def test_developer_comment(self):
        self.profile.addonuser_set.create(addon=self.app)
        note = save_from_email_reply(self.email_base64)
        eq_(note.note_type, comm.DEVELOPER_COMMENT)

    def test_reviewer_comment(self):
        self.grant_permission(self.profile, 'Apps:Review')
        note = save_from_email_reply(self.email_base64)
        eq_(note.note_type, comm.REVIEWER_PUBLIC_COMMENT)

    def test_with_max_count_token(self):
        # Test with an invalid token.
        self.token.update(use_count=comm.MAX_TOKEN_USE_COUNT + 1)
        assert not save_from_email_reply(self.email_base64)

    def test_with_unpermitted_token(self):
        """Test when the token's user does not have a permission on thread."""
        self.profile.groupuser_set.filter(
            group__rules__contains='Apps:Review').delete()
        assert not save_from_email_reply(self.email_base64)

    def test_non_existent_token(self):
        self.token.update(uuid='youtube?v=wn4RP57Y7bw')
        assert not save_from_email_reply(self.email_base64)

    def test_with_invalid_msg(self):
        assert not save_from_email_reply('youtube?v=WwJjts9FzxE')


class TestEmailReplySavingExtensions(TestCase):
    fixtures = fixture('user_999')

    def setUp(self):
        self.extension = extension_factory()
        self.profile = UserProfile.objects.get(pk=999)
        t = CommunicationThread.objects.create(
            _extension=self.extension,
            _extension_version=self.extension.latest_version,
            read_permission_reviewer=True)

        self.token = CommunicationThreadToken.objects.create(
            thread=t, user=self.profile)
        self.token.update(uuid='5a0b8a83d501412589cc5d562334b46b')
        self.email_base64 = open(sample_email).read()
        self.grant_permission(self.profile, 'ContentTools:AddonReview')

    def test_successful_save(self):
        note = save_from_email_reply(self.email_base64)
        eq_(note.body, 'test note 5\n')

    def test_developer_comment(self):
        self.profile.extension_set.add(self.extension)
        note = save_from_email_reply(self.email_base64)
        eq_(note.note_type, comm.DEVELOPER_COMMENT)

    def test_reviewer_comment(self):
        self.grant_permission(self.profile, 'ContentTools:AddonReview')
        note = save_from_email_reply(self.email_base64)
        eq_(note.note_type, comm.REVIEWER_PUBLIC_COMMENT)

    def test_with_max_count_token(self):
        # Test with an invalid token.
        self.token.update(use_count=comm.MAX_TOKEN_USE_COUNT + 1)
        assert not save_from_email_reply(self.email_base64)

    def test_with_unpermitted_token(self):
        """Test when the token's user does not have a permission on thread."""
        self.profile.groupuser_set.all().delete()
        assert not save_from_email_reply(self.email_base64)

    def test_non_existent_token(self):
        self.token.update(uuid='youtube?v=wn4RP57Y7bw')
        assert not save_from_email_reply(self.email_base64)

    def test_with_invalid_msg(self):
        assert not save_from_email_reply('youtube?v=WwJjts9FzxE')


class TestEmailParser(TestCase):

    def test_basic_email(self):
        email_text = open(sample_email).read()
        parser = CommEmailParser(email_text)
        eq_(parser.get_uuid(), '5a0b8a83d501412589cc5d562334b46b')
        eq_(parser.get_body(), 'test note 5\n')

    def test_multipart(self):
        email = open(multi_email).read()
        payload = base64.standard_b64encode(email)
        parser = CommEmailParser(payload)
        eq_(parser.get_body(), 'this is the body text\n')
        eq_(parser.get_uuid(), 'abc123')

    def test_quoted_printable(self):
        email = open(quopri_email).read()
        payload = base64.standard_b64encode(email)
        parser = CommEmailParser(payload)

        body = parser.get_body()
        ok_('Yo,\n\nas it is open source' in body)
        ok_('=20' not in body)
        ok_('appreview@lists.mozilla.org' not in body)

    def test_with_attachments(self):
        for email in (attach_email, attach_email2):
            email = open(attach_email).read()
            payload = base64.standard_b64encode(email)
            parser = CommEmailParser(payload)

            body = parser.get_body()
            ok_('Body inspection' in body)
            eq_(parser.get_uuid(), 'abc123')


class TestEmailNonUsers(TestCase, CommTestMixin):

    def setUp(self):
        self.app = app_factory(
            mozilla_contact='tobias@funke.blue, mae@be.com,')
        self.author = user_factory()

    def _create(self):
        return create_comm_note(self.app, self.app.current_version,
                                self.author, '@ngokevin_')

    def _recipients(self, email_mock):
        recipients = []
        for call in email_mock.call_args_list:
            recipients += call[1]['recipient_list']
        return recipients

    @mock.patch('mkt.comm.utils_mail.send_mail_jinja')
    def test_basic(self, email):
        thread, note = self._create()

        # One for Tobias, one for Maebe.
        eq_(email.call_count, 2)
        eq_(thread.thread_cc.count(), 1)

        recipients = self._recipients(email)
        assert self.author.email not in recipients
        assert 'tobias@funke.blue' in recipients
        assert 'mae@be.com' in recipients

        for call in email.call_args_list:
            ok_('Reply-To' not in call[1]['headers'])


class TestGetMailContextApp(TestCase):

    def setUp(self):
        self.app = app_factory()
        self.user = user_factory()
        self.thread = self.app.threads.create()
        self.note = self.thread.notes.create(thread=self.thread)

    def test_basic(self):
        context = get_mail_context(self.note, self.user.id)
        eq_(context['is_app'], True)
        eq_(context['obj_type'], 'app')

    def test_manage_url(self):
        context = get_mail_context(self.note, self.user.id)
        ok_('developers/app/%s' % self.app.app_slug in context['manage_url'])

    def test_thread_url(self):
        context = get_mail_context(self.note, self.user.id)
        ok_('comm/thread/%s' % self.thread.id in context['thread_url'])


class TestGetMailContextExtension(TestCase):

    def setUp(self):
        self.extension = extension_factory()
        self.user = user_factory()
        self.thread = self.extension.threads.create()
        self.note = self.thread.notes.create()

    def test_basic(self):
        context = get_mail_context(self.note, self.user.id)
        eq_(context['is_extension'], True)
        eq_(context['obj_type'], 'add-on')

    def test_thread_url_developer(self):
        context = get_mail_context(self.note, self.user.id)
        ok_('addon/dashboard/%s' % self.extension.slug in
            context['thread_url'])

    def test_thread_url_reviewer(self):
        self.grant_permission(self.user, 'ContentTools:AddonReview')
        context = get_mail_context(self.note, self.user.id)
        ok_('addon/review/addon/%s' % self.extension.slug in
            context['thread_url'])
