# -*- coding: utf-8 -*-
import os.path

from django.conf import settings

import mock
from nose.tools import eq_

import amo
import amo.tests
from mkt.files.models import File, Platform
from mkt.files.tests.test_models import UploadTest as BaseUploadTest
from mkt.site.fixtures import fixture
from mkt.versions.compare import MAXVERSION, version_dict, version_int
from mkt.versions.models import Version
from mkt.webapps.models import Addon


def test_version_int():
    """Tests that version_int. Corrects our versions."""
    eq_(version_int('3.5.0a1pre2'), 3050000001002)
    eq_(version_int(''), 200100)
    eq_(version_int('0'), 200100)
    eq_(version_int('*'), 99000000200100)
    eq_(version_int(MAXVERSION), MAXVERSION)
    eq_(version_int(MAXVERSION + 1), MAXVERSION)
    eq_(version_int('9999999'), MAXVERSION)


def test_version_int_compare():
    eq_(version_int('3.6.*'), version_int('3.6.99'))
    assert version_int('3.6.*') > version_int('3.6.8')


def test_version_asterix_compare():
    eq_(version_int('*'), version_int('99'))
    assert version_int('98.*') < version_int('*')
    eq_(version_int('5.*'), version_int('5.99'))
    assert version_int('5.*') > version_int('5.0.*')


def test_version_dict():
    eq_(version_dict('5.0'),
        {'major': 5,
         'minor1': 0,
         'minor2': None,
         'minor3': None,
         'alpha': None,
         'alpha_ver': None,
         'pre': None,
         'pre_ver': None})


def test_version_int_unicode():
    eq_(version_int(u'\u2322 ugh stephend'), 200100)


class TestVersion(BaseUploadTest, amo.tests.TestCase):
    fixtures = fixture('webapp_337141', 'platform_all')

    def setUp(self):
        self.version = Version.objects.latest('id')

    def test_developer_name(self):
        version = Version.objects.latest('id')
        version._developer_name = u'M€lâ'
        eq_(version.developer_name, u'M€lâ')
        eq_(Version(_developer_name=u'M€lâ').developer_name, u'M€lâ')

    @mock.patch('mkt.files.utils.parse_addon')
    def test_developer_name_from_upload(self, parse_addon):
        parse_addon.return_value = {
            'version': '42.0',
            'developer_name': u'Mýself'
        }
        addon = Addon.objects.get(pk=337141)
        # Note: we need a valid FileUpload instance, but in the end we are not
        # using its contents since we are mocking parse_addon().
        path = os.path.join(settings.ROOT, 'mkt', 'developers', 'tests',
                            'addons', 'mozball.webapp')
        upload = self.get_upload(abspath=path)
        platform = Platform.objects.get(pk=amo.PLATFORM_ALL.id)
        version = Version.from_upload(upload, addon, [platform])
        eq_(version.version, '42.0')
        eq_(version.developer_name, u'Mýself')

    @mock.patch('mkt.files.utils.parse_addon')
    def test_long_developer_name_from_upload(self, parse_addon):
        truncated_developer_name = u'ý' * 255
        long_developer_name = truncated_developer_name + u'àààà'
        parse_addon.return_value = {
            'version': '42.1',
            'developer_name': long_developer_name
        }
        addon = Addon.objects.get(pk=337141)
        # Note: we need a valid FileUpload instance, but in the end we are not
        # using its contents since we are mocking parse_addon().
        path = os.path.join(settings.ROOT, 'mkt', 'developers', 'tests',
                            'addons', 'mozball.webapp')
        upload = self.get_upload(abspath=path)
        platform = Platform.objects.get(pk=amo.PLATFORM_ALL.id)
        version = Version.from_upload(upload, addon, [platform])
        eq_(version.version, '42.1')
        eq_(version.developer_name, truncated_developer_name)

    def test_is_privileged_hosted_app(self):
        addon = Addon.objects.get(pk=337141)
        eq_(addon.current_version.is_privileged, False)

    @mock.patch('mkt.webapps.models.Webapp.get_manifest_json')
    def test_is_privileged_app(self, get_manifest_json):
        get_manifest_json.return_value = {
            'type': 'privileged'
        }
        addon = Addon.objects.get(pk=337141)
        addon.update(is_packaged=True)
        eq_(addon.current_version.is_privileged, True)

    @mock.patch('mkt.webapps.models.Webapp.get_manifest_json')
    def test_is_privileged_non_privileged_app(self, get_manifest_json):
        get_manifest_json.return_value = {
        }
        addon = Addon.objects.get(pk=337141)
        addon.update(is_packaged=True)
        eq_(addon.current_version.is_privileged, False)

    def test_delete(self):
        version = Version.objects.all()[0]
        eq_(Version.objects.count(), 1)

        version.delete()

        eq_(Version.objects.count(), 0)
        eq_(Version.with_deleted.count(), 1)

        # Ensure deleted version's files get disabled.
        eq_(version.all_files[0].status, amo.STATUS_DISABLED)

    def test_supported_platforms(self):
        assert amo.PLATFORM_ALL in self.version.supported_platforms, (
            'Missing PLATFORM_ALL')

    def test_major_minor(self):
        """Check that major/minor/alpha is getting set."""
        v = Version(version='3.0.12b2')
        eq_(v.major, 3)
        eq_(v.minor1, 0)
        eq_(v.minor2, 12)
        eq_(v.minor3, None)
        eq_(v.alpha, 'b')
        eq_(v.alpha_ver, 2)

        v = Version(version='3.6.1apre2+')
        eq_(v.major, 3)
        eq_(v.minor1, 6)
        eq_(v.minor2, 1)
        eq_(v.alpha, 'a')
        eq_(v.pre, 'pre')
        eq_(v.pre_ver, 2)

        v = Version(version='')
        eq_(v.major, None)
        eq_(v.minor1, None)
        eq_(v.minor2, None)
        eq_(v.minor3, None)

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

    @mock.patch('mkt.versions.models.storage')
    def test_version_delete(self, storage_mock):
        self.version.delete()
        addon = Addon.objects.get(pk=337141)
        assert addon

        assert not Version.objects.filter(addon=addon).exists()
        assert Version.with_deleted.filter(addon=addon).exists()

        assert not storage_mock.delete.called

    @mock.patch('mkt.versions.models.storage')
    def test_packaged_version_delete(self, storage_mock):
        addon = Addon.objects.get(pk=337141)
        addon.update(is_packaged=True)
        version = addon.current_version
        version.delete()

        assert not Version.objects.filter(addon=addon).exists()
        assert Version.with_deleted.filter(addon=addon).exists()

        assert storage_mock.delete.called

    def test_version_delete_files(self):
        eq_(self.version.files.all()[0].status, amo.STATUS_PUBLIC)
        self.version.delete()
        eq_(self.version.files.all()[0].status, amo.STATUS_DISABLED)

    @mock.patch('mkt.files.models.File.hide_disabled_file')
    def test_new_version_disable_old_unreviewed(self, hide_mock):
        addon = Addon.objects.get(pk=337141)
        # The status doesn't change for public files.
        qs = File.objects.filter(version=addon.current_version)
        eq_(qs.all()[0].status, amo.STATUS_PUBLIC)
        Version.objects.create(addon=addon)
        eq_(qs.all()[0].status, amo.STATUS_PUBLIC)
        assert not hide_mock.called

        qs.update(status=amo.STATUS_PENDING)
        version = Version.objects.create(addon=addon)
        version.disable_old_files()
        eq_(qs.all()[0].status, amo.STATUS_DISABLED)
        assert hide_mock.called

    def test_large_version_int(self):
        # This version will fail to be written to the version_int
        # table because the resulting int is bigger than mysql bigint.
        version = Version(addon=Addon.objects.get(pk=337141))
        version.version = '9223372036854775807'
        version.save()
        eq_(version.version_int, None)

    def _reset_version(self, version):
        version.all_files[0].status = amo.STATUS_PUBLIC
        version.deleted = False

    def test_version_is_public(self):
        addon = Addon.objects.get(id=337141)
        version = amo.tests.version_factory(addon=addon)

        # Base test. Everything is in order, the version should be public.
        eq_(version.is_public(), True)

        # Non-public file.
        self._reset_version(version)
        version.all_files[0].status = amo.STATUS_DISABLED
        eq_(version.is_public(), False)

        # Deleted version.
        self._reset_version(version)
        version.deleted = True
        eq_(version.is_public(), False)

        # Non-public addon.
        self._reset_version(version)
        with mock.patch('mkt.webapps.models.Addon.is_public') as is_addon_public:
            is_addon_public.return_value = False
            eq_(version.is_public(), False)

    def test_app_feature_creation_app(self):
        app = Addon.objects.create(type=amo.ADDON_WEBAPP)
        ver = Version.objects.create(addon=app)
        assert ver.features, 'AppFeatures was not created with version.'
