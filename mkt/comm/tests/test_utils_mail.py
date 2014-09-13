import base64
import os.path

from django.conf import settings

from nose.tools import eq_

import amo
from amo.tests import app_factory, TestCase
from mkt.users.models import UserProfile

from mkt.comm.models import CommunicationThread, CommunicationThreadToken
from mkt.comm.utils_mail import CommEmailParser, save_from_email_reply
from mkt.constants import comm
from mkt.site.fixtures import fixture


sample_email = os.path.join(settings.ROOT, 'mkt', 'comm', 'tests',
                            'email.txt')

multi_email = os.path.join(settings.ROOT, 'mkt', 'comm', 'tests',
                           'email_multipart.txt')


class TestEmailReplySaving(TestCase):
    fixtures = fixture('user_999')

    def setUp(self):
        self.app = app_factory(name='Antelope', status=amo.STATUS_PENDING)
        self.profile = UserProfile.objects.get(pk=999)
        t = CommunicationThread.objects.create(
            addon=self.app, version=self.app.current_version,
            read_permission_reviewer=True)

        self.create_switch('comm-dashboard')
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
        eq_(note.note_type, comm.REVIEWER_COMMENT)

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


class TestEmailParser(TestCase):

    def setUp(self):
        email_text = open(sample_email).read()
        self.parser = CommEmailParser(email_text)

    def test_uuid(self):
        eq_(self.parser.get_uuid(), '5a0b8a83d501412589cc5d562334b46b')

    def test_body(self):
        eq_(self.parser.get_body(), 'test note 5\n')

    def test_multipart(self):
        multipart_email = open(multi_email).read()
        payload = base64.standard_b64encode(multipart_email)
        parser = CommEmailParser(payload)
        eq_(parser.get_body(), 'this is the body text\n')
        eq_(parser.get_uuid(), 'abc123')
