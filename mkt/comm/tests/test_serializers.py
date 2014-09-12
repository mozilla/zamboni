from django.conf import settings

from nose.tools import eq_, ok_

import amo
import amo.tests

from mkt.comm import serializers
from mkt.comm.utils import create_comm_note
from mkt.constants import comm


class TestNoteSerializer(amo.tests.TestCase):

    def test_author(self):
        app = amo.tests.app_factory()
        user = amo.tests.user_factory()
        thread, note = create_comm_note(app, app.current_version, user, 'hue')

        data = serializers.NoteSerializer(note, context={
            'request': amo.tests.req_factory_factory()
        }).data
        eq_(data['author_meta']['name'], user.username)
        ok_(data['author_meta']['gravatar_hash'])

    def test_no_author(self):
        app = amo.tests.app_factory()
        thread, note = create_comm_note(app, app.current_version, None, 'hue')

        data = serializers.NoteSerializer(note, context={
            'request': amo.tests.req_factory_factory()
        }).data
        eq_(data['author_meta']['name'], 'System')
        eq_(data['author_meta']['gravatar_hash'], '')
