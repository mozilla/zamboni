# -*- coding: utf-8 -*-
import json
import zipfile


import mock
from nose.tools import eq_

import mkt
import mkt.site.tests

from lib.post_request_task.task import _send_tasks
from mkt.constants import MANIFEST_CONTENT_TYPE
from mkt.webapps.models import Webapp
from mkt.site.fixtures import fixture
from mkt.site.storage_utils import private_storage, public_storage


class TestPackagedManifest(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141', 'group_editor', 'user_editor',
                       'user_editor_group')

    def setUp(self):
        self.app = Webapp.objects.get(pk=337141)
        self.app.update(is_packaged=True)
        # Create a fake package to go along with the app.
        self.latest_file = self.app.get_latest_file()
        with private_storage.open(self.latest_file.file_path,
                                  mode='w') as package:
            test_package = zipfile.ZipFile(package, 'w')
            test_package.writestr('manifest.webapp', 'foobar')
            test_package.close()
        self.latest_file.update(hash=self.latest_file.generate_hash())

        self.url = self.app.get_manifest_url()
        # Don't count things left over from setup, so assertNumQueries will be
        # accurate.
        _send_tasks()

    def tearDown(self):
        public_storage.delete(self.latest_file.file_path)

    def _mocked_json(self):
        data = {
            u'name': u'Packaged App √',
            u'version': u'1.0',
            u'size': 123456,
            u'release_notes': u'Bug fixes',
            u'packaged_path': u'/path/to/file.zip',
        }
        return json.dumps(data)

    def login_as_reviewer(self):
        self.client.logout()
        self.login('editor@mozilla.com')

    def login_as_author(self):
        self.client.logout()
        user = self.app.authors.all()[0]
        self.login(user.email)

    def test_non_packaged(self):
        self.app.update(is_packaged=False)
        res = self.client.get(self.url)
        eq_(res.status_code, 404)

    def test_disabled_by_user(self):
        self.app.update(disabled_by_user=True)
        res = self.client.get(self.url)
        eq_(res.status_code, 404)

    def test_app_pending(self):
        self.app.update(status=mkt.STATUS_PENDING)
        res = self.client.get(self.url)
        eq_(res.status_code, 404)

    def test_app_pending_reviewer(self):
        self.login_as_reviewer()
        self.app.update(status=mkt.STATUS_PENDING)
        res = self.client.get(self.url)
        eq_(res.status_code, 404)

    def test_app_pending_author(self):
        self.login_as_author()
        self.app.update(status=mkt.STATUS_PENDING)
        res = self.client.get(self.url)
        eq_(res.status_code, 404)

    @mock.patch('mkt.webapps.models.Webapp.get_cached_manifest')
    def test_app_unlisted(self, _mock):
        _mock.return_value = (self._mocked_json(), 'fake_etag')
        self.app.update(status=mkt.STATUS_UNLISTED)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)

    @mock.patch('mkt.webapps.models.Webapp.get_cached_manifest')
    def test_app_unlisted_reviewer(self, _mock):
        _mock.return_value = (self._mocked_json(), 'fake_etag')
        self.login_as_reviewer()
        self.app.update(status=mkt.STATUS_UNLISTED)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)

    @mock.patch('mkt.webapps.models.Webapp.get_cached_manifest')
    def test_app_unlisted_author(self, _mock):
        _mock.return_value = (self._mocked_json(), 'fake_etag')
        self.login_as_author()
        self.app.update(status=mkt.STATUS_UNLISTED)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)

    def test_app_private(self):
        self.app.update(status=mkt.STATUS_APPROVED)
        res = self.client.get(self.url)
        eq_(res.status_code, 404)

    @mock.patch('mkt.webapps.models.Webapp.get_cached_manifest')
    def test_app_private_reviewer(self, _mock):
        _mock.return_value = (self._mocked_json(), 'fake_etag')
        self.login_as_reviewer()
        self.app.update(status=mkt.STATUS_APPROVED)
        res = self.client.get(self.url)
        eq_(res.status_code, 404)

    @mock.patch('mkt.webapps.models.Webapp.get_cached_manifest')
    def test_app_private_author(self, _mock):
        _mock.return_value = (self._mocked_json(), 'fake_etag')
        self.login_as_author()
        self.app.update(status=mkt.STATUS_APPROVED)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)

    @mock.patch('mkt.webapps.models.Webapp.get_cached_manifest')
    def test_app_public(self, _mock):
        _mock.return_value = (self._mocked_json(), 'fake_etag')
        res = self.client.get(self.url)
        eq_(res.content, self._mocked_json())
        eq_(res['Content-Type'], MANIFEST_CONTENT_TYPE)
        eq_(res['ETag'], '"fake_etag"')

    @mock.patch('mkt.webapps.models.Webapp.get_cached_manifest')
    def test_conditional_get(self, _mock):
        _mock.return_value = (self._mocked_json(), 'fake_etag')
        res = self.client.get(self.url, HTTP_IF_NONE_MATCH='"fake_etag"')
        eq_(res.content, '')
        eq_(res.status_code, 304)

    @mock.patch('mkt.webapps.models.Webapp.get_cached_manifest')
    def test_logged_out(self, _mock):
        _mock.return_value = (self._mocked_json(), 'fake_etag')
        self.client.logout()
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        eq_(res['Content-Type'], MANIFEST_CONTENT_TYPE)

    @mock.patch('mkt.webapps.models.Webapp.get_cached_manifest')
    def test_has_cors(self, _mock):
        _mock.return_value = (self._mocked_json(), 'fake_etag')
        res = self.client.get(self.url)
        self.assertCORS(res, 'get')

    @mock.patch('mkt.webapps.utils.public_storage')
    @mock.patch('mkt.webapps.models.packaged')
    def test_calls_sign(self, _packaged, _storage):
        _packaged.sign.return_value = '/path/to/signed.zip'
        _storage.size.return_value = 1234
        self.client.get(self.url)
        assert _packaged.sign.called

    @mock.patch('mkt.webapps.models.Webapp.get_cached_manifest')
    def test_queries(self, _mock):
        """
        We explicitly want to avoid wanting to use all the query transforms
        since we don't need them here.

        The queries we are expecting are:
          * 2 savepoints
          * 2 addons - 1 for the addon, and 1 for the translations

        """
        _mock.return_value = (self._mocked_json(), 'fake_etag')
        with self.assertNumQueries(4):
            res = self.client.get(self.url)
            eq_(res.status_code, 200)
