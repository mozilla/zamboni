# -*- coding: utf-8 -*-
import os.path

from django.conf import settings

import mock
from nose.tools import eq_

import mkt
import mkt.site.tests
from mkt.files.models import File
from mkt.files.tests.test_models import UploadTest as BaseUploadTest
from mkt.site.fixtures import fixture
from mkt.site.utils import version_factory
from mkt.versions.models import Version
from mkt.webapps.models import Webapp


class TestVersion(BaseUploadTest, mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        self.version = Version.objects.latest('id')

    def test_developer_name(self):
        version = Version.objects.latest('id')
        version._developer_name = u'M€lâ'
        eq_(version.developer_name, u'M€lâ')
        eq_(Version(_developer_name=u'M€lâ').developer_name, u'M€lâ')

    @mock.patch('mkt.files.utils.parse_webapp')
    def test_developer_name_from_upload(self, parse_webapp):
        parse_webapp.return_value = {
            'version': '42.0',
            'developer_name': u'Mýself'
        }
        webapp = Webapp.objects.get(pk=337141)
        # Note: we need a valid FileUpload instance, but in the end we are not
        # using its contents since we are mocking parse_webapp().
        path = os.path.join(settings.ROOT, 'mkt', 'developers', 'tests',
                            'webapps', 'mozball.webapp')
        upload = self.get_upload(abspath=path)
        version = Version.from_upload(upload, webapp)
        eq_(version.version, '42.0')
        eq_(version.developer_name, u'Mýself')

    @mock.patch('mkt.files.utils.parse_webapp')
    def test_long_developer_name_from_upload(self, parse_webapp):
        truncated_developer_name = u'ý' * 255
        long_developer_name = truncated_developer_name + u'àààà'
        parse_webapp.return_value = {
            'version': '42.1',
            'developer_name': long_developer_name
        }
        webapp = Webapp.objects.get(pk=337141)
        # Note: we need a valid FileUpload instance, but in the end we are not
        # using its contents since we are mocking parse_webapp().
        path = os.path.join(settings.ROOT, 'mkt', 'developers', 'tests',
                            'webapps', 'mozball.webapp')
        upload = self.get_upload(abspath=path)
        version = Version.from_upload(upload, webapp)
        eq_(version.version, '42.1')
        eq_(version.developer_name, truncated_developer_name)

    def test_is_privileged_hosted_app(self):
        webapp = Webapp.objects.get(pk=337141)
        eq_(webapp.current_version.is_privileged, False)

    @mock.patch('mkt.webapps.models.Webapp.get_manifest_json')
    def test_is_privileged_app(self, get_manifest_json):
        get_manifest_json.return_value = {
            'type': 'privileged'
        }
        webapp = Webapp.objects.get(pk=337141)
        webapp.update(is_packaged=True)
        eq_(webapp.current_version.is_privileged, True)

    @mock.patch('mkt.webapps.models.Webapp.get_manifest_json')
    def test_is_privileged_non_privileged_app(self, get_manifest_json):
        get_manifest_json.return_value = {
        }
        webapp = Webapp.objects.get(pk=337141)
        webapp.update(is_packaged=True)
        eq_(webapp.current_version.is_privileged, False)

    def test_delete(self):
        version = Version.objects.all()[0]
        eq_(Version.objects.count(), 1)

        version.delete()

        eq_(Version.objects.count(), 0)
        eq_(Version.with_deleted.count(), 1)

        # Ensure deleted version's files get disabled.
        eq_(version.all_files[0].status, mkt.STATUS_DISABLED)

    def test_has_files(self):
        assert self.version.has_files, 'Version with files not recognized.'

        self.version.files.all().delete()
        self.version = Version.objects.latest('id')
        assert not self.version.has_files, (
            'Version without files not recognized.')

    def _get_version(self, status):
        v = Version()
        v.all_files = [mock.Mock()]
        v.all_files[0].status = status
        return v

    @mock.patch('mkt.versions.models.public_storage')
    def test_version_delete(self, storage_mock):
        self.version.delete()
        webapp = Webapp.objects.get(pk=337141)
        assert webapp

        assert not Version.objects.filter(webapp=webapp).exists()
        assert Version.with_deleted.filter(webapp=webapp).exists()

        assert not storage_mock.delete.called

    @mock.patch('mkt.versions.models.public_storage')
    def test_packaged_version_delete(self, storage_mock):
        webapp = Webapp.objects.get(pk=337141)
        webapp.update(is_packaged=True)
        version = webapp.current_version
        version.delete()

        assert not Version.objects.filter(webapp=webapp).exists()
        assert Version.with_deleted.filter(webapp=webapp).exists()

        assert storage_mock.delete.called

    def test_version_delete_files(self):
        eq_(self.version.files.all()[0].status, mkt.STATUS_PUBLIC)
        self.version.delete()
        eq_(self.version.files.all()[0].status, mkt.STATUS_DISABLED)

    @mock.patch('mkt.files.models.File.hide_disabled_file')
    def test_new_version_disable_old_unreviewed(self, hide_mock):
        webapp = Webapp.objects.get(pk=337141)
        # The status doesn't change for public files.
        qs = File.objects.filter(version=webapp.current_version)
        eq_(qs.all()[0].status, mkt.STATUS_PUBLIC)
        Version.objects.create(webapp=webapp)
        eq_(qs.all()[0].status, mkt.STATUS_PUBLIC)
        assert not hide_mock.called

        qs.update(status=mkt.STATUS_PENDING)
        version = Version.objects.create(webapp=webapp)
        version.disable_old_files()
        eq_(qs.all()[0].status, mkt.STATUS_DISABLED)
        assert hide_mock.called

    def _reset_version(self, version):
        version.all_files[0].status = mkt.STATUS_PUBLIC
        version.deleted = False

    def test_version_is_public(self):
        webapp = Webapp.objects.get(id=337141)
        version = version_factory(webapp=webapp)

        # Base test. Everything is in order, the version should be public.
        eq_(version.is_public(), True)

        # Non-public file.
        self._reset_version(version)
        version.all_files[0].status = mkt.STATUS_DISABLED
        eq_(version.is_public(), False)

        # Deleted version.
        self._reset_version(version)
        version.deleted = True
        eq_(version.is_public(), False)

        # Non-public webapp.
        self._reset_version(version)
        with mock.patch('mkt.webapps.models.Webapp.is_public') \
                as is_webapp_public:
            is_webapp_public.return_value = False
            eq_(version.is_public(), False)

    def test_app_feature_creation_app(self):
        app = Webapp.objects.create()
        ver = Version.objects.create(webapp=app)
        assert ver.features, 'AppFeatures was not created with version.'
