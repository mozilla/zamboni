import mock
from nose.tools import eq_

from mkt.constants.base import STATUS_PUBLIC
from mkt.extensions.models import Extension, ExtensionVersion
from mkt.extensions.tasks import fetch_icon
from mkt.site.tests import TestCase


class TestFetchIcon(TestCase):
    def setUp(self):
        super(TestFetchIcon, self).setUp()
        self.extension = Extension.objects.create()
        self.version = self.extension.versions.create(manifest={
            'icons': {
                '128': '/path/to/icon.png'
            }
        }, version='0.1')

    @mock.patch('mkt.extensions.tasks.save_icon')
    @mock.patch('mkt.extensions.tasks.ZipFile')
    @mock.patch('mkt.extensions.tasks.private_storage')
    def _test(self, private_storage_mock, ZipFile_mock, save_icon_mock,
              **kwargs):
        fetch_icon(self.extension.pk, **kwargs)

        # We've opened file_path.
        eq_(private_storage_mock.open.call_count, 1)
        eq_(private_storage_mock.open.call_args_list[0][0],
            (self.version.file_path, ))

        # We've used it as a zip file, looking for the 128 icon (stripping
        # leading '/').
        eq_(ZipFile_mock.call_count, 1)
        eq_(ZipFile_mock.call_args_list[0][0],
            (private_storage_mock.open().__enter__.return_value, ))
        eq_(ZipFile_mock().__enter__().read.call_count, 1)
        eq_(ZipFile_mock().__enter__().read.call_args_list[0][0],
            ('path/to/icon.png', ))

        # We've passed the extension and icon contents to save_icon.
        eq_(save_icon_mock.call_count, 1)
        eq_(save_icon_mock.call_args_list[0][0],
            (self.extension, ZipFile_mock().__enter__().read.return_value, ))

    @mock.patch('mkt.extensions.tasks.save_icon')
    @mock.patch('mkt.extensions.tasks.ZipFile')
    @mock.patch('mkt.extensions.tasks.private_storage')
    def _test_nothing_called(self, private_storage_mock, ZipFile_mock,
                             save_icon_mock, **kwargs):
        fetch_icon(self.extension.pk, **kwargs)
        eq_(private_storage_mock.open.call_count, 0)
        eq_(ZipFile_mock.call_count, 0)
        eq_(save_icon_mock.call_count, 0)

    def test_with_explicit_version_pk(self):
        self._test(version_pk=self.version.pk)

    def test_no_version_fallback_no_public_version(self):
        with self.assertRaises(ExtensionVersion.DoesNotExist):
            self._test_nothing_called()

    def test_no_version_fallback_to_latest_public_version(self):
        with mock.patch('mkt.extensions.models.fetch_icon'):
            # mocking fetch_icon() to prevent it from being called
            # automatically as the version is made public.
            self.version.update(status=STATUS_PUBLIC)
        self._test()

    def test_no_icon_in_manifest(self):
        self.version.update(manifest={})
        self._test_nothing_called(version_pk=self.version.pk)

    def test_no_128_icon_in_manifest(self):
        self.version.update(manifest={'icons': {'64': '/path/to/64.png'}})
        self._test_nothing_called(version_pk=self.version.pk)
