# -*- coding: utf-8 -*-
import os
import re
import zipfile

from django import forms
from django.conf import settings
from django.core.cache import cache
from django.core.urlresolvers import reverse

from mock import Mock, patch
from nose.tools import eq_

from mkt.files.helpers import FileViewer, DiffHelper
from mkt.files.utils import SafeUnzip
from mkt.site.storage_utils import (copy_stored_file, local_storage,
                                    private_storage, storage_is_remote)
from mkt.site.tests import MktPaths, TestCase


root = os.path.join(settings.ROOT, 'mkt/files/fixtures/files')


def get_file(x):
    return '%s/%s' % (root, x)


def make_file(pk, file_path, **kwargs):
    obj = Mock()
    obj.id = pk
    for k, v in kwargs.items():
        setattr(obj, k, v)
    obj.file_path = file_path
    obj.__str__ = lambda x: x.pk
    obj.version = Mock()
    obj.version.version = 1
    return obj


# TODO: It'd be nice if these used packaged app examples but these addons still
# flex the code so it wasn't converted.
class TestFileHelper(TestCase):

    def setUp(self):
        fn = get_file('dictionary-test.xpi')
        if storage_is_remote():
            copy_stored_file(
                fn, fn,
                src_storage=local_storage, dst_storage=private_storage)
        self.viewer = FileViewer(make_file(1, fn))

    def tearDown(self):
        self.viewer.cleanup()

    def test_files_not_extracted(self):
        eq_(self.viewer.is_extracted(), False)

    def test_files_extracted(self):
        self.viewer.extract()
        eq_(self.viewer.is_extracted(), True)

    def test_cleanup(self):
        self.viewer.extract()
        self.viewer.cleanup()
        eq_(self.viewer.is_extracted(), False)

    def test_truncate(self):
        truncate = self.viewer.truncate
        for x, y in (['foo.rdf', 'foo.rdf'],
                     ['somelongfilename.rdf', 'somelongfilenam...rdf'],
                     [u'unicode삮.txt', u'unicode\uc0ae.txt'],
                     [u'unicodesomelong삮.txt', u'unicodesomelong...txt'],
                     ['somelongfilename.somelongextension',
                      'somelongfilenam...somelonge..'],):
            eq_(truncate(x), y)

    def test_get_files_not_extracted(self):
        assert not self.viewer.get_files()

    def test_get_files_size(self):
        self.viewer.extract()
        files = self.viewer.get_files()
        eq_(len(files), 15)

    def test_get_files_directory(self):
        self.viewer.extract()
        files = self.viewer.get_files()
        eq_(files['install.js']['directory'], False)
        eq_(files['install.js']['binary'], False)
        eq_(files['__MACOSX']['directory'], True)
        eq_(files['__MACOSX']['binary'], False)

    def test_url_file(self):
        self.viewer.extract()
        files = self.viewer.get_files()
        url = reverse('mkt.files.list', args=[self.viewer.file.id, 'file',
                                              'install.js'])
        assert files['install.js']['url'].endswith(url)

    def test_get_files_depth(self):
        self.viewer.extract()
        files = self.viewer.get_files()
        eq_(files['dictionaries/license.txt']['depth'], 1)

    def test_bom(self):
        dest = os.path.join(settings.TMP_PATH, 'test_bom')
        with private_storage.open(dest, 'w') as f:
            f.write('foo'.encode('utf-16'))
        self.viewer.select('foo')
        self.viewer.selected = {'full': dest, 'size': 1}
        eq_(self.viewer.read_file(), u'foo')
        private_storage.delete(dest)

    def test_syntax(self):
        for filename, syntax in [('foo.rdf', 'xml'),
                                 ('foo.xul', 'xml'),
                                 ('foo.json', 'js'),
                                 ('foo.jsm', 'js'),
                                 ('foo.js', 'js'),
                                 ('manifest.webapp', 'js'),
                                 ('foo.html', 'html'),
                                 ('foo.css', 'css'),
                                 ('foo.bar', 'plain')]:
            eq_(self.viewer.get_syntax(filename), syntax)

    def test_file_order(self):
        self.viewer.extract()
        dest = self.viewer.dest
        private_storage.open(os.path.join(dest, 'manifest.webapp'),
                             'w').close()
        subdir = os.path.join(dest, 'chrome')
        with private_storage.open(os.path.join(subdir, 'foo'), 'w') as f:
            f.write('.')
        if not private_storage.exists(subdir):
            # Might be on S3, which doesn't have directories (and
            # django-storages doesn't support empty files).
            with private_storage.open(subdir, 'w') as f:
                f.write('.')
        cache.clear()
        files = self.viewer.get_files().keys()
        rt = files.index(u'chrome')
        eq_(files[rt:rt + 3], [u'chrome', u'chrome/foo', u'dictionaries'])

    @patch.object(settings, 'FILE_VIEWER_SIZE_LIMIT', 5)
    def test_file_size(self):
        self.viewer.extract()
        self.viewer.get_files()
        self.viewer.select('install.js')
        res = self.viewer.read_file()
        eq_(res, '')
        assert self.viewer.selected['msg'].startswith('File size is')

    @patch.object(settings, 'FILE_VIEWER_SIZE_LIMIT', 5)
    def test_file_size_unicode(self):
        with self.activate(locale='he'):
            self.viewer.extract()
            self.viewer.get_files()
            self.viewer.select('install.js')
            res = self.viewer.read_file()
            eq_(res, '')
            assert self.viewer.selected['msg'].startswith('File size is')

    @patch.object(settings, 'FILE_UNZIP_SIZE_LIMIT', 5)
    def test_contents_size(self):
        self.assertRaises(forms.ValidationError, self.viewer.extract)

    def test_default(self):
        eq_(self.viewer.get_default(None), 'manifest.webapp')

    def test_delete_mid_read(self):
        self.viewer.extract()
        self.viewer.select('install.js')
        private_storage.delete(os.path.join(self.viewer.dest, 'install.js'))
        res = self.viewer.read_file()
        eq_(res, '')
        assert self.viewer.selected['msg'].startswith('That file no')

    @patch('mkt.files.helpers.get_md5')
    def test_delete_mid_tree(self, get_md5):
        get_md5.side_effect = IOError('ow')
        self.viewer.extract()
        eq_({}, self.viewer.get_files())


class TestDiffHelper(TestCase, MktPaths):

    def setUp(self):
        src = self.packaged_app_path('signed.zip')
        if storage_is_remote():
            copy_stored_file(
                src, src,
                src_storage=local_storage, dst_storage=private_storage)
        self.helper = DiffHelper(make_file(1, src), make_file(2, src))

    def tearDown(self):
        self.helper.cleanup()
        if storage_is_remote():
            private_storage.delete(self.packaged_app_path('signed.zip'))

    def test_files_not_extracted(self):
        eq_(self.helper.is_extracted(), False)

    def test_files_extracted(self):
        self.helper.extract()
        eq_(self.helper.is_extracted(), True)

    def test_get_files(self):
        eq_(self.helper.left.get_files(),
            self.helper.get_files())

    def test_diffable(self):
        self.helper.extract()
        self.helper.select('index.html')
        assert self.helper.is_diffable()

    def test_diffable_one_missing(self):
        self.helper.extract()
        private_storage.delete(os.path.join(self.helper.right.dest,
                                            'index.html'))
        self.helper.select('index.html')
        assert self.helper.is_diffable()

    def test_diffable_allow_empty(self):
        self.helper.extract()
        self.assertRaises(AssertionError, self.helper.right.read_file)
        eq_(self.helper.right.read_file(allow_empty=True), '')

    def test_diffable_both_missing(self):
        self.helper.extract()
        self.helper.select('foo.js')
        assert not self.helper.is_diffable()

    def test_diffable_deleted_files(self):
        self.helper.extract()
        private_storage.delete(os.path.join(self.helper.left.dest,
                                            'index.html'))
        eq_('index.html' in self.helper.get_deleted_files(), True)

    def test_diffable_one_binary_same(self):
        self.helper.extract()
        self.helper.select('main.js')
        self.helper.left.selected['binary'] = True
        assert self.helper.is_binary()

    def test_diffable_one_binary_diff(self):
        self.helper.extract()
        self.change(self.helper.left.dest, 'asd')
        cache.clear()
        self.helper.select('main.js')
        self.helper.left.selected['binary'] = True
        assert self.helper.is_binary()

    def test_diffable_two_binary_diff(self):
        self.helper.extract()
        self.change(self.helper.left.dest, 'asd')
        self.change(self.helper.right.dest, 'asd123')
        cache.clear()
        self.helper.select('main.js')
        self.helper.left.selected['binary'] = True
        self.helper.right.selected['binary'] = True
        assert self.helper.is_binary()

    def test_diffable_one_directory(self):
        self.helper.extract()
        self.helper.select('main.js')
        self.helper.left.selected['directory'] = True
        assert not self.helper.is_diffable()
        assert self.helper.left.selected['msg'].startswith('This file')

    def test_diffable_parent(self):
        self.helper.extract()
        self.change(self.helper.left.dest, 'asd',
                    filename='META-INF/ids.json')
        cache.clear()
        files = self.helper.get_files()
        eq_(files['META-INF/ids.json']['diff'], True)
        eq_(files['META-INF']['diff'], True)

    def change(self, file, text, filename='main.js'):
        path = os.path.join(file, filename)
        data = private_storage.open(path, 'r').read()
        data += text
        with private_storage.open(path, 'w') as f:
            f.write(data)


class TestSafeUnzipFile(TestCase, MktPaths):

    # TODO(andym): get full coverage for existing SafeUnzip methods, most
    # is covered in the file viewer tests.
    @patch.object(settings, 'FILE_UNZIP_SIZE_LIMIT', 5)
    def test_unzip_individual_file_size_limit(self):
        zip = SafeUnzip(self.packaged_app_path('full-tpa.zip'))
        self.assertRaises(forms.ValidationError, zip.is_valid)

    @patch.object(settings, 'FILE_UNZIP_SIZE_LIMIT', 100 * 1024)
    def test_unzip_total_file_size_limit(self):
        # There are no files over 100 kb in that zip, but the total is over.
        zip = SafeUnzip(self.packaged_app_path('full-tpa.zip'))
        self.assertRaises(forms.ValidationError, zip.is_valid)

    def test_unzip_fatal(self):
        zip = SafeUnzip(self.manifest_path('mozball.webapp'))
        self.assertRaises(zipfile.BadZipfile, zip.is_valid)

    def test_unzip_not_fatal(self):
        zip = SafeUnzip(self.manifest_path('mozball.webapp'))
        assert not zip.is_valid(fatal=False)

    def test_extract_path(self):
        zip = SafeUnzip(self.packaged_app_path('mozball.zip'))
        assert zip.is_valid()
        desc_string = '"description": "Exciting Open Web development action!"'
        assert desc_string in zip.extract_path('manifest.webapp')

    def test_not_secure(self):
        zip = SafeUnzip(self.packaged_app_path('mozball.zip'))
        zip.is_valid()
        assert not zip.is_signed()

    def test_is_secure(self):
        zip = SafeUnzip(self.packaged_app_path('signed.zip'))
        zip.is_valid()
        assert zip.is_signed()

    def test_is_broken(self):
        zip = SafeUnzip(self.packaged_app_path('signed.zip'))
        zip.is_valid()
        sf_re = re.compile('^META\-INF/(\w+)\.sf$')
        for info in zip.info:
            if sf_re.match(info.filename):
                info.filename = 'META-INF/foo.foo'
                break
        assert not zip.is_signed()
