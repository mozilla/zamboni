# -*- coding: utf-8 -*-
import hashlib
import json
import os

from django.conf import settings

import mock
from nose.tools import eq_, ok_

import mkt
import mkt.site.tests
from mkt.files.models import File, FileUpload, FileValidation, nfd_str
from mkt.site.fixtures import fixture
from mkt.site.storage_utils import (copy_stored_file, local_storage,
                                    private_storage, public_storage)
from mkt.site.utils import chunked
from mkt.versions.models import Version
from mkt.webapps.models import Webapp


class UploadCreationMixin(object):
    def upload(self, name, **kwargs):
        if os.path.splitext(name)[-1] not in ['.webapp', '.zip']:
            name = name + '.zip'

        v = json.dumps(dict(errors=0, warnings=1, notices=2, metadata={}))
        fname = nfd_str(self.packaged_app_path(name))
        if not local_storage.exists(fname):
            raise ValueError('The file %s does not exist :(', fname)
        if not private_storage.exists(fname):
            copy_stored_file(fname, fname, src_storage=local_storage,
                             dst_storage=private_storage)
        data = {
            'path': fname,
            'name': name,
            'hash': 'sha256:%s' % name,
            'validation': v
        }
        data.update(**kwargs)
        return FileUpload.objects.create(**data)


class UploadTest(mkt.site.tests.TestCase, mkt.site.tests.MktPaths):
    """
    Base for tests that mess with file uploads, safely using temp directories.
    """
    def get_upload(self, filename=None, abspath=None, validation=None,
                   user=None):
        zip = open(abspath).read()
        upload = FileUpload.from_post([zip], filename=abspath or filename,
                                      size=1234)
        # Simulate what fetch_manifest() does after uploading an app.
        upload.validation = (validation or
                             json.dumps(dict(errors=0, warnings=1, notices=2,
                                             metadata={}, messages=[])))
        if user:
            upload.user = user
        upload.save()
        return upload


class TestFileUpload(UploadTest):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        super(TestFileUpload, self).setUp()
        self.data = 'file contents'

    def upload(self):
        # The data should be in chunks.
        data = [''.join(x) for x in chunked(self.data, 3)]
        return FileUpload.from_post(data, 'filename.zip', len(self.data))

    def test_from_post_write_file(self):
        eq_(private_storage.open(self.upload().path).read(), self.data)

    def test_from_post_filename(self):
        eq_(self.upload().name, 'filename.zip')

    def test_from_post_hash(self):
        hash = hashlib.sha256(self.data).hexdigest()
        eq_(self.upload().hash, 'sha256:%s' % hash)

    def test_save_without_validation(self):
        f = FileUpload.objects.create()
        assert not f.valid

    def test_save_with_validation(self):
        f = FileUpload.objects.create(
            validation='{"errors": 0, "metadata": {}}')
        assert f.valid

        f = FileUpload.objects.create(validation='wtf')
        assert not f.valid

    def test_update_with_validation(self):
        f = FileUpload.objects.create()
        f.validation = '{"errors": 0, "metadata": {}}'
        f.save()
        assert f.valid

    def test_update_without_validation(self):
        f = FileUpload.objects.create()
        f.save()
        assert not f.valid

    def test_ascii_names(self):
        fu = FileUpload.from_post('', u'mözball.zip', 0)
        assert 'zip' in fu.name

        fu = FileUpload.from_post('', u'мозила_србија-0.11.zip', 0)
        assert 'zip' in fu.name

        fu = FileUpload.from_post('', u'フォクすけといっしょ.zip', 0)
        assert 'zip' in fu.name

        fu = FileUpload.from_post('', u'\u05d0\u05d5\u05e1\u05e3.zip', 0)
        assert 'zip' in fu.name


class TestFileFromUpload(UploadCreationMixin, UploadTest):

    def setUp(self):
        super(TestFileFromUpload, self).setUp()
        self.addon = Webapp.objects.create(name='app name')
        self.version = Version.objects.create(addon=self.addon)

    def test_filename_hosted(self):
        upload = self.upload('mozball')
        f = File.from_upload(upload, self.version)
        eq_(f.filename, 'app-name-0.1.webapp')

    def test_filename_packaged(self):
        self.addon.is_packaged = True
        upload = self.upload('mozball')
        f = File.from_upload(upload, self.version)
        eq_(f.filename, 'app-name-0.1.zip')

    def test_file_validation(self):
        upload = self.upload('mozball')
        file = File.from_upload(upload, self.version)
        fv = FileValidation.objects.get(file=file)
        eq_(fv.validation, upload.validation)
        eq_(fv.valid, True)
        eq_(fv.errors, 0)
        eq_(fv.warnings, 1)
        eq_(fv.notices, 2)

    def test_file_hash(self):
        upload = self.upload('mozball')
        f = File.from_upload(upload, self.version)
        # Hash should have been stolen from the fileupload.
        eq_(f.hash, 'sha256:mozball.zip')

        upload = self.upload('mozball')
        f = File.from_upload(upload, self.version)
        # Hash should have been stolen from the fileupload again.
        eq_(f.hash, 'sha256:mozball.zip')

    def test_utf8(self):
        upload = self.upload(u'mozball')
        self.version.addon.name = u'mözball'
        f = File.from_upload(upload, self.version)
        eq_(f.filename, u'app-name-0.1.webapp')

    def test_size(self):
        upload = self.upload('mozball')
        f = File.from_upload(upload, self.version)
        eq_(f.size, 93594)


class TestFile(mkt.site.tests.TestCase, mkt.site.tests.MktPaths):
    """
    Tests the methods of the File model.
    """
    fixtures = fixture('webapp_337141')

    def test_get_absolute_url(self):
        f = File.objects.get()
        url = f.get_absolute_url(src='src')
        expected = '/downloads/file/81555/steamcube.webapp?src=src'
        assert url.endswith(expected), url

    def check_delete(self, file_, filename):
        """Test that when the File object is deleted, it is removed from the
        filesystem."""
        try:
            with public_storage.open(filename, 'w') as f:
                f.write('sample data\n')
            assert public_storage.exists(filename)
            file_.delete()
            assert not public_storage.exists(filename)
        finally:
            if public_storage.exists(filename):
                public_storage.delete(filename)

    def test_delete_by_version(self):
        f = File.objects.get()
        version = f.version
        self.check_delete(version, f.file_path)

    def test_delete_file_path(self):
        f = File.objects.get()
        self.check_delete(f, f.file_path)

    def test_delete_no_file(self):
        """Test that the file object can be deleted without the file being
        present."""
        f = File.objects.get()
        filename = f.file_path
        assert not public_storage.exists(filename), ('File exists at: %s' %
                                                     filename)
        f.delete()

    def test_delete_signal(self):
        """Test that if there's no filename, the signal is ok."""
        f = File.objects.get()
        f.update(filename='')
        f.delete()

    @mock.patch('mkt.files.models.File.hide_disabled_file')
    def test_disable_signal(self, hide_mock):
        f = File.objects.get()
        f.status = mkt.STATUS_PUBLIC
        f.save()
        assert not hide_mock.called

        f.status = mkt.STATUS_DISABLED
        f.save()
        assert hide_mock.called

    @mock.patch('mkt.files.models.File.hide_disabled_file')
    def test_reject_signal(self, hide_mock):
        f = File.objects.get()
        f.status = mkt.STATUS_PUBLIC
        f.save()
        assert not hide_mock.called

        f.status = mkt.STATUS_REJECTED
        f.save()
        assert hide_mock.called

    @mock.patch('mkt.files.models.File.unhide_disabled_file')
    def test_unhide_on_enable(self, unhide_mock):
        f = File.objects.get()
        f.status = mkt.STATUS_PUBLIC
        f.save()
        assert not unhide_mock.called

        f = File.objects.get()
        f.status = mkt.STATUS_DISABLED
        f.save()
        assert not unhide_mock.called

        f = File.objects.get()
        f.status = mkt.STATUS_PUBLIC
        f.save()
        assert unhide_mock.called

    def test_unhide_disabled_files(self):
        f = File.objects.get()
        f.status = mkt.STATUS_PUBLIC
        with private_storage.open(f.guarded_file_path, 'wb') as fp:
            fp.write('some data\n')
        f.unhide_disabled_file()
        assert public_storage.exists(f.file_path)
        assert public_storage.open(f.file_path).size

    def test_generate_filename(self):
        f = File.objects.get()
        eq_(f.generate_filename(), 'something-something-1.0.webapp')

    def test_generate_filename_packaged_app(self):
        f = File.objects.get()
        f.version.addon.app_slug = 'testing-123'
        f.version.addon.is_packaged = True
        eq_(f.generate_filename(), 'testing-123-1.0.zip')

    def test_generate_webapp_fn_non_ascii(self):
        f = File()
        f.version = Version(version='0.1.7')
        f.version.addon = Webapp(app_slug=u' フォクすけ  といっしょ')
        eq_(f.generate_filename(), 'app-0.1.7.webapp')

    def test_generate_webapp_fn_partial_non_ascii(self):
        f = File()
        f.version = Version(version='0.1.7')
        f.version.addon = Webapp(app_slug=u'myapp フォクすけ  といっしょ')
        eq_(f.generate_filename(), 'myapp-0.1.7.webapp')

    def test_generate_filename_ja(self):
        f = File()
        f.version = Version(version='0.1.7')
        f.version.addon = Webapp(name=u' フォクすけ  といっしょ')
        eq_(f.generate_filename(), 'none-0.1.7.webapp')

    def clean_files(self, f):
        if not public_storage.exists(f.file_path):
            with public_storage.open(f.file_path, 'w') as fp:
                fp.write('sample data\n')

    @mock.patch('mkt.files.models.private_storage')
    def test_generate_hash(self, storage_mock):
        f = File()
        f.version = Version()
        # Mock remote storage to use a local file instead of a remote one.
        storage_mock.open = open
        filename = self.packaged_app_path('mozball.zip')
        assert f.generate_hash(filename).startswith('sha256:ad85d6316166d4')

    def test_addon(self):
        f = File.objects.get()
        addon_id = f.version.addon_id
        addon = Webapp.objects.get(pk=addon_id)
        addon.update(status=mkt.STATUS_DELETED)
        eq_(f.addon.id, addon_id)

    def test_disabled_file_uses_guarded_path(self):
        f = File.objects.get()
        f.update(status=mkt.STATUS_DISABLED)
        ok_(settings.GUARDED_ADDONS_PATH in f.file_path)
        ok_(settings.ADDONS_PATH not in f.file_path)


class TestSignedPath(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        self.file_ = File.objects.get(pk=81555)

    def test_path(self):
        path = (self.file_.file_path
                    .replace('.webapp', '.signed.webapp')
                    .replace(settings.ADDONS_PATH, settings.SIGNED_APPS_PATH))
        eq_(self.file_.signed_file_path, path)

    def test_reviewer_path(self):
        path = (self.file_.file_path
                    .replace('.webapp', '.signed.webapp')
                    .replace(settings.ADDONS_PATH,
                             settings.SIGNED_APPS_REVIEWER_PATH))
        eq_(self.file_.signed_reviewer_file_path, path)
