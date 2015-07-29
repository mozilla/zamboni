from django.conf import settings
from django.core.urlresolvers import reverse
from django.test.utils import override_settings

import mock
from nose.tools import eq_

import mkt
from lib.crypto import packaged
from lib.crypto.tests import mock_sign
from mkt.site.fixtures import fixture
from mkt.submit.tests.test_views import BasePackagedAppTest


class TestDownload(BasePackagedAppTest):
    fixtures = fixture('webapp_337141', 'user_999',
                       'user_admin', 'group_admin', 'user_admin_group')

    def setUp(self):
        super(TestDownload, self).setUp()
        super(TestDownload, self).setup_files()
        self.url = reverse('downloads.file', args=[self.file.pk])

    @override_settings(XSENDFILE=True)
    @mock.patch.object(packaged, 'sign', mock_sign)
    def test_download(self):
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        assert settings.XSENDFILE_HEADER in res

    @override_settings(XSENDFILE=True)
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

    @mock.patch('lib.crypto.packaged.sign')
    def test_not_public_but_owner(self, sign):
        self.login('steamcube@mozilla.com')
        self.file.update(status=mkt.STATUS_PENDING)
        eq_(self.client.get(self.url).status_code, 200)
        assert not sign.called

    @mock.patch('lib.crypto.packaged.sign')
    def test_not_public_not_owner(self, sign):
        self.login('regular@mozilla.com')
        self.file.update(status=mkt.STATUS_PENDING)
        eq_(self.client.get(self.url).status_code, 404)

    @mock.patch.object(packaged, 'sign', mock_sign)
    def test_disabled_but_owner(self):
        self.login('steamcube@mozilla.com')
        eq_(self.client.get(self.url).status_code, 200)

    @mock.patch.object(packaged, 'sign', mock_sign)
    def test_disabled_but_admin(self):
        self.login('admin@mozilla.com')
        eq_(self.client.get(self.url).status_code, 200)

    @override_settings(XSENDFILE=True)
    @mock.patch.object(packaged, 'sign', mock_sign)
    def test_file_blocklisted(self):
        self.file.update(status=mkt.STATUS_BLOCKED)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        assert settings.XSENDFILE_HEADER in res

    def test_has_cors(self):
        self.assertCORS(self.client.get(self.url), 'get')
