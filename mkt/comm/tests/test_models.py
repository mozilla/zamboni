from datetime import datetime
from os import path

from django.core.exceptions import ValidationError
from django.core.urlresolvers import NoReverseMatch
from django.test.utils import override_settings

from nose.tools import eq_, ok_

import mkt
from mkt.comm.models import (CommAttachment, CommunicationNote,
                             CommunicationThread, CommunicationThreadCC,
                             CommunicationThreadToken, user_has_perm_app,
                             user_has_perm_note, user_has_perm_thread)
from mkt.comm.tests.test_views import CommTestMixin
from mkt.constants import comm as const
from mkt.site.fixtures import fixture
from mkt.site.tests import TestCase, extension_factory, user_factory
from mkt.webapps.models import Webapp
from mkt.users.models import UserProfile


TESTS_DIR = path.dirname(path.abspath(__file__))
ATTACHMENTS_DIR = path.join(TESTS_DIR, 'attachments')


class PermissionTestMixin(object):
    fixtures = fixture('user_999', 'webapp_337141')

    def setUp(self):
        self.addon = Webapp.objects.get()
        self.version = self.addon.current_version
        self.user = UserProfile.objects.get(email='regular@mozilla.com')

        self.thread = CommunicationThread.objects.create(
            _addon=self.addon, _version=self.version)
        self.author = user_factory(email='lol')
        self.note = CommunicationNote.objects.create(
            thread=self.thread, author=self.author, note_type=0, body='xyz')
        self.obj = None

    def _eq_obj_perm(self, val):
        if self.type == 'note':
            eq_(user_has_perm_note(self.obj, self.user), val)
        else:
            eq_(user_has_perm_thread(self.obj, self.user), val)

    def test_no_perm(self):
        self._eq_obj_perm(False)

    def test_has_perm_public(self):
        self.obj.update(read_permission_public=True)
        self._eq_obj_perm(True)

    def test_has_perm_dev(self):
        self.obj.update(read_permission_developer=True)
        self.addon.addonuser_set.create(user=self.user)
        self._eq_obj_perm(True)

    def test_has_perm_rev_addons(self):
        self.obj.update(read_permission_reviewer=True)
        self.grant_permission(self.user, 'Apps:Review')
        self._eq_obj_perm(True)

    def test_has_perm_rev_ext(self):
        self.obj.update(read_permission_reviewer=True)
        self.grant_permission(self.user, 'ContentTools:AddonReview')
        self._eq_obj_perm(True)

    def test_has_perm_senior_rev(self):
        self.obj.update(read_permission_senior_reviewer=True)
        self.grant_permission(self.user, 'Apps:ReviewEscalated')
        self._eq_obj_perm(True)

    def test_has_perm_moz_contact(self):
        self.obj.update(read_permission_mozilla_contact=True)
        self.addon.update(
            mozilla_contact=','.join([self.user.email, 'lol@lol.com']))
        self._eq_obj_perm(True)

    def test_has_perm_staff(self):
        self.obj.update(read_permission_staff=True)
        self.grant_permission(self.user, 'Admin:*')
        self._eq_obj_perm(True)


class TestCommunicationNote(PermissionTestMixin, TestCase):

    def setUp(self):
        super(TestCommunicationNote, self).setUp()
        self.type = 'note'
        self.obj = self.note

    def test_has_perm_author(self):
        self.obj.update(author=self.user)
        self._eq_obj_perm(True)

    def test_has_perm_no_author(self):
        self.obj.update(author=None)
        self._eq_obj_perm(False)

    def test_manager(self):
        eq_(CommunicationNote.objects.count(), 1)
        eq_(CommunicationNote.objects.with_perms(self.user,
                                                 self.thread).count(), 0)

        self.note.update(author=self.user)
        eq_(CommunicationNote.objects.with_perms(self.user,
                                                 self.thread).count(), 1)


class TestCommunicationThread(PermissionTestMixin, TestCase):

    def setUp(self):
        super(TestCommunicationThread, self).setUp()
        self.type = 'thread'
        self.obj = self.thread

    def test_addon_deleted(self):
        self.thread.obj.update(status=mkt.STATUS_DELETED)
        eq_(self.thread.obj, self.addon)

    def test_version_deleted(self):
        self.version.update(deleted=True)
        eq_(self.thread.version, self.version)

    def test_has_perm_posted(self):
        self.note.update(author=self.user)
        self._eq_obj_perm(True)

    def test_has_perm_cc(self):
        CommunicationThreadCC.objects.create(user=self.user, thread=self.obj)
        self._eq_obj_perm(True)

    def test_has_perm_app_reviewer(self):
        ok_(not user_has_perm_app(self.user, self.addon))
        self.grant_permission(self.user, 'Apps:Review')
        ok_(user_has_perm_app(self.user, self.addon))

    def test_has_perm_app_developer(self):
        ok_(not user_has_perm_app(self.user, self.addon))
        self.addon.addonuser_set.create(user=self.user)
        ok_(user_has_perm_app(self.user, self.addon))

    def test_clean(self):
        with self.assertRaises(ValidationError):
            # Need app.
            CommunicationThread.objects.create().clean()

        with self.assertRaises(ValidationError):
            # Need version.
            CommunicationThread.objects.create(_addon=self.addon).clean()


class TestCommunicationThreadExtension(TestCase):
    fixtures = fixture('user_999',)

    def setUp(self):
        self.extension = extension_factory()
        self.version = self.extension.latest_version
        self.user = UserProfile.objects.get(email='regular@mozilla.com')

        self.thread = CommunicationThread.objects.create(
            _extension=self.extension, _extension_version=self.version)
        self.author = user_factory(email='lol')
        self.note = CommunicationNote.objects.create(
            thread=self.thread, author=self.author, note_type=0, body='xyz')

    def test_fields(self):
        ok_(not self.thread._addon)
        ok_(not self.thread._version)

    def test_obj(self):
        eq_(self.thread.obj, self.extension)

    def test_version(self):
        eq_(self.thread.version, self.version)

    def test_clean(self):
        with self.assertRaises(ValidationError):
            # Need extension version.
            CommunicationThread.objects.create(
                _extension=self.extension).clean()


class TestThreadTokenModel(TestCase):
    fixtures = fixture('user_999', 'webapp_337141')

    def setUp(self):
        addon = Webapp.objects.get(pk=337141)
        self.thread = CommunicationThread(_addon=addon)
        user = UserProfile.objects.all()[0]
        self.token = CommunicationThreadToken(thread=self.thread, user=user)
        self.token.modified = datetime.now()
        self.token.use_count = 0

    def test_live_thread_token_is_valid(self):
        """
        Test `is_valid()` when the token is fresh (not expired).
        """
        assert self.token.is_valid()

    def test_expired_thread_token_is_valid(self):
        """
        Test `is_valid()` when the token has expired.
        """
        self.token.modified = self.days_ago(const.THREAD_TOKEN_EXPIRY + 1)
        assert not self.token.is_valid()

    def test_unused_token_is_valid(self):
        """
        Test `is_valid()` when the token is unused.
        """
        assert self.token.is_valid()

    def test_max_used_thread_token_is_valid(self):
        """
        Test `is_valid()` when the token has been fully used.
        """
        self.token.use_count = const.MAX_TOKEN_USE_COUNT
        assert not self.token.is_valid()

    def test_reset_uuid(self):
        """
        Test `reset_uuid()` generates a differ uuid.
        """
        self.thread.save()
        self.token.thread = self.thread
        self.token.save()
        uuid = self.token.uuid
        assert uuid

        self.token.reset_uuid()
        assert self.token.uuid
        assert uuid != self.token.uuid


class TestCommAttachment(TestCase, CommTestMixin):
    fixtures = fixture('webapp_337141')
    XSS_STRING = 'MMM <script>alert(bacon);</script>'

    def setUp(self):
        self.user = user_factory(email='porkbelly')
        mkt.set_user(self.user)
        self.profile = self.user
        self.addon = Webapp.objects.get()
        self.version = self.addon.latest_version
        self.thread = self._thread_factory()
        self.note = self._note_factory(self.thread)
        self.attachment1, self.attachment2 = self._attachments(self.note)

    def _attachments(self, note):
        """
        Create and return a tuple of CommAttachment instances.
        """
        ala1 = CommAttachment.objects.create(note=note,
                                             filepath='bacon.txt',
                                             mimetype='text/plain')
        ala2 = CommAttachment.objects.create(note=note,
                                             filepath='bacon.jpg',
                                             description=self.XSS_STRING,
                                             mimetype='image/jpeg')
        return ala1, ala2

    def test_filename(self):
        msg = 'CommAttachment().filename() returning incorrect filename.'
        eq_(self.attachment1.filename(), 'bacon.txt', msg)
        eq_(self.attachment2.filename(), 'bacon.jpg', msg)

    def test_full_path_dirname(self):
        msg = 'CommAttachment().full_path() returning incorrect path.'
        FAKE_PATH = '/tmp/attachments/'
        with self.settings(REVIEWER_ATTACHMENTS_PATH=FAKE_PATH):
            eq_(self.attachment1.full_path(), FAKE_PATH + 'bacon.txt', msg)
            eq_(self.attachment2.full_path(), FAKE_PATH + 'bacon.jpg', msg)

    def test_display_name(self):
        msg = ('CommAttachment().display_name() returning '
               'incorrect display name.')
        eq_(self.attachment1.display_name(), 'bacon.txt', msg)

    def test_display_name_xss(self):
        ok_('<script>' not in self.attachment2.display_name())

    @override_settings(REVIEWER_ATTACHMENTS_PATH=ATTACHMENTS_DIR)
    def test_is_image(self):
        msg = 'CommAttachment().is_image() not correctly detecting images.'
        eq_(self.attachment1.is_image(), False, msg)
        eq_(self.attachment2.is_image(), True, msg)

    def test_get_absolute_url(self):
        try:
            self.attachment1.get_absolute_url()
            self.attachment2.get_absolute_url()
        except NoReverseMatch:
            assert False, 'CommAttachment.get_absolute_url NoReverseMatch'
