from django.conf import settings
from django.core.urlresolvers import reverse
from django.test.utils import override_settings

import mock
from nose.tools import eq_

import mkt
from lib.post_request_task.task import _send_tasks
from lib.crypto import packaged
from lib.crypto.tests import mock_sign
from mkt.site.fixtures import fixture
from mkt.submit.tests.test_views import BasePackagedAppTest
from mkt.site.storage_utils import (copy_stored_file, local_storage,
                                    private_storage, public_storage)


class TestDownload(BasePackagedAppTest):
    fixtures = fixture('webapp_337141', 'user_999',
                       'user_admin', 'group_admin', 'user_admin_group')

    def setUp(self):
        super(TestDownload, self).setUp()
        super(TestDownload, self).setup_files()
        self.url = reverse('downloads.file', args=[self.file.pk])
        # Don't count things left over from setup, so assertNumQueries will be
        # accurate.
        _send_tasks()

    @override_settings(
        DEFAULT_FILE_STORAGE='mkt.site.storage_utils.S3BotoPrivateStorage'
    )
    @mock.patch.object(packaged, 'sign', mock_sign)
    def test_download(self):
        res = self.client.get(self.url)
        path = public_storage.url(self.file.signed_file_path)
        self.assert3xx(res, path)
        assert settings.XSENDFILE_HEADER not in res

    @override_settings(
        XSENDFILE=True,
        DEFAULT_FILE_STORAGE='mkt.site.storage_utils.LocalFileStorage'
    )
    @mock.patch.object(packaged, 'sign', mock_sign)
    def test_download_local_storage(self):
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        assert settings.XSENDFILE_HEADER in res
        eq_(res['X-Accel-Redirect'], self.file.signed_file_path)

    @override_settings(
        XSENDFILE=True,
        DEFAULT_FILE_STORAGE='mkt.site.storage_utils.LocalFileStorage'
    )
    def test_download_already_signed(self):
        self.client.logout()

        with mock.patch.object(packaged, 'sign', mock_sign):
            # Sign the app before downloading, like it would normally happen.
            self.app.sign_if_packaged(self.file.version_id)
        # Now download and look at the number of queries.
        with self.assertNumQueries(2):
            res = self.client.get(self.url)
        eq_(res.status_code, 200)
        assert settings.XSENDFILE_HEADER in res

    def test_disabled(self):
        self.app.update(status=mkt.STATUS_DISABLED)
        eq_(self.client.get(self.url).status_code, 404)

    def test_not_public(self):
        self.file.update(status=mkt.STATUS_PENDING)
        eq_(self.client.get(self.url).status_code, 404)

    @override_settings(
        DEFAULT_FILE_STORAGE='mkt.site.storage_utils.S3BotoPrivateStorage'
    )
    @mock.patch('lib.crypto.packaged.sign')
    def test_not_public_but_owner(self, sign):
        self.login('steamcube@mozilla.com')
        self.file.update(status=mkt.STATUS_PENDING)
        path = private_storage.url(self.file.file_path)
        res = self.client.get(self.url)
        self.assert3xx(res, path)
        assert not sign.called

    @mock.patch('lib.crypto.packaged.sign')
    def test_not_public_not_owner(self, sign):
        self.login('regular@mozilla.com')
        self.file.update(status=mkt.STATUS_PENDING)
        eq_(self.client.get(self.url).status_code, 404)

    @override_settings(
        DEFAULT_FILE_STORAGE='mkt.site.storage_utils.S3BotoPrivateStorage'
    )
    @mock.patch.object(packaged, 'sign', mock_sign)
    def test_disabled_but_owner(self):
        self.login('steamcube@mozilla.com')
        self.file.update(status=mkt.STATUS_DISABLED)
        copy_stored_file(self.packaged_app_path('mozball.zip'),
                         self.file.file_path,
                         src_storage=local_storage,
                         dst_storage=private_storage)
        path = private_storage.url(self.file.file_path)
        res = self.client.get(self.url)
        self.assert3xx(res, path)

    @override_settings(
        DEFAULT_FILE_STORAGE='mkt.site.storage_utils.S3BotoPrivateStorage'
    )
    @mock.patch.object(packaged, 'sign', mock_sign)
    def test_rejected_but_owner(self):
        self.login('steamcube@mozilla.com')
        self.file.update(status=mkt.STATUS_REJECTED)
        copy_stored_file(self.packaged_app_path('mozball.zip'),
                         self.file.file_path,
                         src_storage=local_storage,
                         dst_storage=private_storage)
        path = private_storage.url(self.file.file_path)
        res = self.client.get(self.url)
        self.assert3xx(res, path)

    @override_settings(
        DEFAULT_FILE_STORAGE='mkt.site.storage_utils.S3BotoPrivateStorage'
    )
    @mock.patch.object(packaged, 'sign', mock_sign)
    def test_disabled_but_admin(self):
        self.login('admin@mozilla.com')
        self.file.update(status=mkt.STATUS_DISABLED)
        copy_stored_file(self.packaged_app_path('mozball.zip'),
                         self.file.file_path,
                         src_storage=local_storage,
                         dst_storage=private_storage)
        path = private_storage.url(self.file.file_path)
        res = self.client.get(self.url)
        self.assert3xx(res, path)

    @override_settings(
        XSENDFILE=True,
        DEFAULT_FILE_STORAGE='mkt.site.storage_utils.LocalFileStorage'
    )
    @mock.patch.object(packaged, 'sign', mock_sign)
    def test_file_blocklisted(self):
        self.file.update(status=mkt.STATUS_BLOCKED)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        assert settings.XSENDFILE_HEADER in res

    def test_has_cors(self):
        self.assertCORS(self.client.get(self.url), 'get')
