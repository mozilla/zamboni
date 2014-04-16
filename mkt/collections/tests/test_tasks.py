import json
import mock
from tempfile import mkdtemp

from django.test.utils import override_settings
from nose.tools import eq_

import amo
import amo.tests
from mkt.collections.models import Collection
from mkt.collections.tasks import dump_collection, dump_collections
from mkt.webapps.tasks import rm_directory
from mkt.site.fixtures import fixture

temp_directory = mkdtemp()


@override_settings(DUMPED_APPS_PATH=temp_directory)
class TestDumpCollections(amo.tests.TestCase):
    fixtures = fixture('webapp_337141', 'collection_81721')

    def get_collection(self):
        return Collection.objects.get(pk=81721)

    def tearDown(self):
        rm_directory(temp_directory)

    def test_dump_collections(self):
        filename = dump_collections([81721])[0]
        collection_json = json.load(open(filename, 'r'))
        eq_(collection_json['id'], 81721)
        eq_(collection_json['slug'], 'public-apps')

    def test_dump_collection(self):
        collection = self.get_collection()
        filename = dump_collection(collection)
        collection_json = json.load(open(filename, 'r'))
        eq_(collection_json['id'], 81721)
        eq_(collection_json['slug'], 'public-apps')

    @mock.patch('mkt.collections.tasks.dump_collection')
    def test_dumps_public_collection(self, dump_collection):
        dump_collections([81721])
        assert dump_collection.called

    @mock.patch('mkt.collections.tasks.dump_collection')
    def test_doesnt_dump_public_collection(self, dump_collection):
        collection = self.get_collection()
        collection.update(is_public=False)
        dump_collections([81721])
        assert not dump_collection.called
