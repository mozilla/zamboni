from nose.tools import eq_, ok_

from mkt.comm import serializers
from mkt.comm.utils import create_comm_note
from mkt.site.tests import req_factory_factory, TestCase, user_factory
from mkt.site.utils import app_factory


class TestNoteSerializer(TestCase):

    def test_author(self):
        app = app_factory()
        user = user_factory(display_name='Bob')
        thread, note = create_comm_note(app, app.current_version, user, 'hue')

        data = serializers.NoteSerializer(note, context={
            'request': req_factory_factory()
        }).data
        eq_(data['author_meta']['name'], 'Bob')
        ok_(data['author_meta']['gravatar_hash'])

    def test_no_author(self):
        app = app_factory()
        thread, note = create_comm_note(app, app.current_version, None, 'hue')

        data = serializers.NoteSerializer(note, context={
            'request': req_factory_factory()
        }).data
        eq_(data['author_meta']['name'], 'Mozilla')
        eq_(data['author_meta']['gravatar_hash'], '')
