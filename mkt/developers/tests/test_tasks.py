import codecs
import json
import os
import shutil
import socket
import subprocess
import tempfile
from contextlib import contextmanager
from cStringIO import StringIO

from django.conf import settings
from django.core import mail
from django.core.files.storage import default_storage as storage
from django.core.urlresolvers import reverse
from django.test.utils import override_settings

import mock
from nose.tools import eq_, ok_
from PIL import Image
from requests import RequestException

import mkt
import mkt.site.tests
from mkt.users.models import UserProfile
from mkt.developers import tasks
from mkt.files.models import FileUpload
from mkt.site.fixtures import fixture
from mkt.site.tests.test_utils_ import get_image_path
from mkt.site.utils import app_factory, ImageCheck
from mkt.submit.tests.test_views import BaseWebAppTest
from mkt.webapps.models import AddonExcludedRegion as AER
from mkt.webapps.models import Preview, Webapp


def test_resize_icon_shrink():
    """ Image should be shrunk so that the longest side is 32px. """

    resize_size = [32]
    final_size = [(32, 12)]

    _uploader(resize_size, final_size)


def test_resize_icon_enlarge():
    """ Image stays the same, since the new size is bigger than both sides. """

    resize_size = [1000]
    final_size = [(339, 128)]

    _uploader(resize_size, final_size)


def test_resize_icon_same():
    """ Image stays the same, since the new size is the same. """

    resize_size = [339]
    final_size = [(339, 128)]

    _uploader(resize_size, final_size)


def test_resize_icon_list():
    """ Resize multiple images at once. """

    resize_size = [32, 82, 100]
    final_size = [(32, 12), (82, 30), (100, 37)]

    _uploader(resize_size, final_size)


def _uploader(resize_size, final_size):
    img = get_image_path('mozilla.png')
    original_size = (339, 128)

    for rsize, fsize in zip(resize_size, final_size):
        dest_name = os.path.join(settings.ADDON_ICONS_PATH, '1234')
        src = tempfile.NamedTemporaryFile(mode='r+w+b', suffix='.png',
                                          delete=False)
        # resize_icon removes the original, copy it to a tempfile and use that.
        shutil.copyfile(img, src.name)
        # Sanity check.
        with storage.open(src.name) as fp:
            src_image = Image.open(fp)
            src_image.load()
        eq_(src_image.size, original_size)

        val = tasks.resize_icon(src.name, dest_name, resize_size, locally=True)
        eq_(val, {'icon_hash': 'bb362450'})
        with storage.open('%s-%s.png' % (dest_name, rsize)) as fp:
            dest_image = Image.open(fp)
            dest_image.load()

        # Assert that the width is always identical.
        eq_(dest_image.size[0], fsize[0])
        # Assert that the height can be a wee bit fuzzy.
        assert -1 <= dest_image.size[1] - fsize[1] <= 1, (
            'Got width %d, expected %d' % (
                fsize[1], dest_image.size[1]))

        if os.path.exists(dest_image.filename):
            os.remove(dest_image.filename)
        assert not os.path.exists(dest_image.filename)

    assert not os.path.exists(src.name)


class TestPngcrushImage(mkt.site.tests.TestCase):

    def setUp(self):
        img = get_image_path('mozilla.png')
        self.src = tempfile.NamedTemporaryFile(mode='r+w+b', suffix=".png",
                                               delete=False)
        shutil.copyfile(img, self.src.name)

        patcher = mock.patch('subprocess.Popen')
        self.mock_popen = patcher.start()
        attrs = {
            'returncode': 0,
            'communicate.return_value': ('ouput', 'error')
        }
        self.mock_popen.return_value.configure_mock(**attrs)
        self.addCleanup(patcher.stop)

    def tearDown(self):
        os.remove(self.src.name)

    @mock.patch('shutil.move')
    def test_pngcrush_image_is_called(self, mock_move):
        name = self.src.name
        expected_suffix = '.opti.png'
        expected_cmd = ['pngcrush', '-q', '-rem', 'alla', '-brute', '-reduce',
                        '-e', expected_suffix, name]

        rval = tasks.pngcrush_image(name)
        self.mock_popen.assert_called_once_with(
            expected_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE,
            stdout=subprocess.PIPE)
        mock_move.assert_called_once_with(
            '%s%s' % (os.path.splitext(name)[0], expected_suffix), name)
        eq_(rval, {'image_hash': 'bb362450'})

    @mock.patch('mkt.webapps.models.Webapp.update')
    @mock.patch('shutil.move')
    def test_set_modified(self, mock_move, update_mock):
        """Test passed instance is updated with the hash."""
        name = self.src.name
        obj = app_factory()

        ret = tasks.pngcrush_image(name, 'some_hash', set_modified_on=[obj])
        ok_('some_hash' in ret)
        eq_(update_mock.call_args_list[-1][1]['some_hash'], ret['some_hash'])
        ok_('modified' in update_mock.call_args_list[-1][1])


class TestValidator(mkt.site.tests.TestCase):

    def setUp(self):
        self.upload = FileUpload.objects.create()
        self.upload.add_file(['test data'], 'example.txt', 9)
        assert not self.upload.valid

    def get_upload(self):
        return FileUpload.objects.get(pk=self.upload.pk)

    @mock.patch('mkt.developers.tasks.run_validator')
    def test_pass_validation(self, _mock):
        _mock.return_value = '{"errors": 0}'
        tasks.validator(self.upload.pk)
        assert self.get_upload().valid

    @mock.patch('mkt.developers.tasks.run_validator')
    def test_fail_validation(self, _mock):
        _mock.return_value = '{"errors": 2}'
        tasks.validator(self.upload.pk)
        assert not self.get_upload().valid

    @mock.patch('mkt.developers.tasks.run_validator')
    def test_validation_error(self, _mock):
        _mock.side_effect = Exception
        eq_(self.upload.task_error, None)
        tasks.validator(self.upload.pk)
        error = self.get_upload().task_error
        assert error is not None
        assert error.startswith('Traceback (most recent call last)'), error

    @mock.patch('mkt.developers.tasks.validate_app')
    @mock.patch('mkt.developers.tasks.storage.open')
    def test_validate_manifest(self, _open, _mock):
        _open.return_value = tempfile.TemporaryFile()
        _mock.return_value = '{"errors": 0}'
        tasks.validator(self.upload.pk)
        assert _mock.called

    @mock.patch('mkt.developers.tasks.validate_packaged_app')
    @mock.patch('zipfile.is_zipfile')
    def test_validate_packaged_app(self, _zipfile, _mock):
        _zipfile.return_value = True
        _mock.return_value = '{"errors": 0}'
        tasks.validator(self.upload.pk)
        assert _mock.called


storage_open = storage.open


def _mock_hide_64px_icon(path, *args, **kwargs):
    """
    A function that mocks `storage.open` and throws an IOError if you try to
    open a 128x128px icon.
    """
    if '128' in path:
        raise IOError('No 128px icon for you!')
    return storage_open(path, *args, **kwargs)


@override_settings(
    PREVIEW_FULL_PATH='/tmp/uploads-tests/previews/full/%s/%d.%s',
    PREVIEW_THUMBNAIL_PATH='/tmp/uploads-tests/previews/thumbs/%s/%d.png')
class TestResizePreview(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        # Make sure there are no leftover files in the test directory before
        # launching tests that depend on the files presence/absence.
        shutil.rmtree('/tmp/uploads-tests/previews/', ignore_errors=True)

    def get_image(self, filename):
        """Copy image to tmp and return tmp path.

        We do this because the task `resize_preview` removes the src file when
        finished.

        """
        src = get_image_path(filename)
        dst = os.path.join(settings.TMP_PATH, 'preview', filename)
        shutil.copy(src, dst)
        return dst

    def test_preview(self):
        addon = Webapp.objects.get(pk=337141)
        preview = Preview.objects.create(addon=addon)
        src = self.get_image('preview.jpg')
        tasks.resize_preview(src, preview.pk)
        preview = preview.reload()
        eq_(preview.image_size, [400, 533])
        eq_(preview.thumbnail_size, [100, 133])
        eq_(preview.is_landscape, False)
        with storage.open(preview.thumbnail_path) as fp:
            im = Image.open(fp)
            eq_(list(im.size), [100, 133])
        with storage.open(preview.image_path) as fp:
            im = Image.open(fp)
            eq_(list(im.size), [400, 533])

    def test_preview_rotated(self):
        addon = Webapp.objects.get(pk=337141)
        preview = Preview.objects.create(addon=addon)
        src = self.get_image('preview_landscape.jpg')
        tasks.resize_preview(src, preview.pk)
        preview = preview.reload()
        eq_(preview.image_size, [533, 400])
        eq_(preview.thumbnail_size, [133, 100])
        eq_(preview.is_landscape, True)
        with storage.open(preview.thumbnail_path) as fp:
            im = Image.open(fp)
            eq_(list(im.size), [133, 100])
        with storage.open(preview.image_path) as fp:
            im = Image.open(fp)
            eq_(list(im.size), [533, 400])

    def test_preview_dont_generate_image(self):
        addon = Webapp.objects.get(pk=337141)
        preview = Preview.objects.create(addon=addon)
        src = self.get_image('preview.jpg')
        tasks.resize_preview(src, preview.pk, generate_image=False)
        preview = preview.reload()
        eq_(preview.image_size, [])
        eq_(preview.thumbnail_size, [100, 133])
        eq_(preview.sizes, {u'thumbnail': [100, 133]})
        with storage.open(preview.thumbnail_path) as fp:
            im = Image.open(fp)
            eq_(list(im.size), [100, 133])
        assert not os.path.exists(preview.image_path), preview.image_path


class TestFetchManifest(mkt.site.tests.TestCase):

    def setUp(self):
        self.upload = FileUpload.objects.create()
        self.content_type = 'application/x-web-app-manifest+json'

        patcher = mock.patch('mkt.developers.tasks.requests.get')
        self.requests_mock = patcher.start()
        self.addCleanup(patcher.stop)

    def get_upload(self):
        return FileUpload.objects.get(pk=self.upload.pk)

    def file(self, name):
        return os.path.join(os.path.dirname(__file__), 'addons', name)

    @contextmanager
    def patch_requests(self):
        response_mock = mock.Mock(status_code=200)
        response_mock.iter_content.return_value = mock.Mock(
            next=lambda: '<default>')
        response_mock.headers = {'content-type': self.content_type}
        yield response_mock
        self.requests_mock.return_value = response_mock

    @mock.patch('mkt.developers.tasks.validator')
    def test_success_add_file(self, validator_mock):
        with self.patch_requests() as ur:
            ur.iter_content.return_value = mock.Mock(next=lambda: 'woo')

        tasks.fetch_manifest('http://xx.com/manifest.json', self.upload.pk)
        upload = FileUpload.objects.get(pk=self.upload.pk)
        eq_(upload.name, 'http://xx.com/manifest.json')
        eq_(storage.open(upload.path).read(), 'woo')

    @mock.patch('mkt.developers.tasks.validator')
    def test_success_call_validator(self, validator_mock):
        with self.patch_requests() as ur:
            ct = self.content_type + '; charset=utf-8'
            ur.headers = {'content-type': ct}

        tasks.fetch_manifest('http://xx.com/manifest.json', self.upload.pk)
        assert validator_mock.called
        assert self.requests_mock.called
        eq_(self.requests_mock.call_args[1]['headers'], tasks.REQUESTS_HEADERS)

    def check_validation(self, msg=''):
        upload = self.get_upload()
        if msg:
            validation = json.loads(upload.validation)
            eq_([m['message'] for m in validation['messages']], [msg])
            eq_(validation['errors'], 1)
            eq_(validation['success'], False)
            eq_(len(validation['messages']), 1)
        else:
            validation_output = upload.validation
            if not validation_output:
                return
            validation = json.loads(validation_output)
            assert not validation['messages']
            eq_(validation['errors'], 0)
            eq_(validation['success'], True)

    def test_connection_error(self):
        reason = socket.gaierror(8, 'nodename nor servname provided')
        self.requests_mock.side_effect = RequestException(reason)
        tasks.fetch_manifest('url', self.upload.pk)
        self.check_validation(
            'No manifest was found at that URL. Check the address and try '
            'again.')

    def test_url_timeout(self):
        reason = socket.timeout('too slow')
        self.requests_mock.side_effect = RequestException(reason)
        tasks.fetch_manifest('url', self.upload.pk)
        self.check_validation(
            'No manifest was found at that URL. Check the address and try '
            'again.')

    def test_other_url_error(self):
        reason = Exception('Some other failure.')
        self.requests_mock.side_effect = RequestException(reason)
        tasks.fetch_manifest('url', self.upload.pk)
        self.check_validation(
            'No manifest was found at that URL. Check the address and try '
            'again.')

    @mock.patch('mkt.developers.tasks.validator', lambda uid, **kw: None)
    def test_no_content_type(self):
        with self.patch_requests() as ur:
            ur.headers = {}

        tasks.fetch_manifest('url', self.upload.pk)
        self.check_validation(
            'No manifest was found at that URL. Check the address and try '
            'again.')

    @mock.patch('mkt.developers.tasks.validator', lambda uid, **kw: None)
    def test_bad_content_type(self):
        with self.patch_requests() as ur:
            ur.headers = {'Content-Type': 'x'}

        tasks.fetch_manifest('url', self.upload.pk)
        self.check_validation(
            'Manifests must be served with the HTTP header "Content-Type: '
            'application/x-web-app-manifest+json". See %s for more '
            'information.' % tasks.CT_URL)

    @mock.patch('mkt.developers.tasks.validator', lambda uid, **kw: None)
    def test_good_charset(self):
        with self.patch_requests() as ur:
            ur.headers = {
                'content-type': 'application/x-web-app-manifest+json;'
                                'charset=utf-8'
            }

        tasks.fetch_manifest('url', self.upload.pk)
        self.check_validation()

    @mock.patch('mkt.developers.tasks.validator', lambda uid, **kw: None)
    def test_bad_charset(self):
        with self.patch_requests() as ur:
            ur.headers = {
                'content-type': 'application/x-web-app-manifest+json;'
                                'charset=ISO-1234567890-LOL'
            }

        tasks.fetch_manifest('url', self.upload.pk)
        self.check_validation("The manifest's encoding does not match the "
                              'charset provided in the HTTP Content-Type.')

    def test_response_too_large(self):
        with self.patch_requests() as ur:
            content = 'x' * (settings.MAX_WEBAPP_UPLOAD_SIZE + 1)
            ur.iter_content.return_value = mock.Mock(next=lambda: content)

        tasks.fetch_manifest('url', self.upload.pk)
        max_webapp_size = settings.MAX_WEBAPP_UPLOAD_SIZE
        self.check_validation('Your manifest must be less than %s bytes.' %
                              max_webapp_size)

    @mock.patch('mkt.developers.tasks.validator', lambda uid, **kw: None)
    def test_http_error(self):
        with self.patch_requests() as ur:
            ur.status_code = 404

        tasks.fetch_manifest('url', self.upload.pk)
        self.check_validation(
            'No manifest was found at that URL. Check the address and try '
            'again.')

    def test_strip_utf8_bom(self):
        with self.patch_requests() as ur:
            with open(self.file('utf8bom.webapp')) as fp:
                content = fp.read()
                ur.iter_content.return_value = mock.Mock(next=lambda: content)

        tasks.fetch_manifest('url', self.upload.pk)

        # Should not be called with anything else (e.g., `decode_unicode`).
        ur.iter_content.assert_called_with(
            chunk_size=settings.MAX_WEBAPP_UPLOAD_SIZE + 1)

        upload = self.get_upload()
        with storage.open(upload.path, 'rb') as fp:
            manifest = fp.read()
            json.loads(manifest)  # No parse error.
            assert not manifest.startswith(codecs.BOM_UTF8)

    def test_non_utf8_encoding(self):
        with self.patch_requests() as ur:
            with open(self.file('utf8bom.webapp')) as fp:
                # Set encoding to utf16 which will be invalid.
                content = fp.read().decode('utf8').encode('utf16')
                ur.iter_content.return_value = mock.Mock(next=lambda: content)
        tasks.fetch_manifest('url', self.upload.pk)
        self.check_validation(
            'Your manifest file was not encoded as valid UTF-8.')


class TestFetchIcon(BaseWebAppTest):

    def setUp(self):
        super(TestFetchIcon, self).setUp()
        self.content_type = 'image/png'
        self.apps_path = os.path.join(settings.ROOT, 'mkt', 'developers',
                                      'tests', 'addons')
        patcher = mock.patch('mkt.developers.tasks.requests.get')
        self.requests_mock = patcher.start()
        self.requests_mock.return_value = StringIO('mozballin')
        self.addCleanup(patcher.stop)

    def webapp_from_path(self, path):
        self.upload = self.get_upload(abspath=path,
                                      user=UserProfile.objects.get(pk=999))
        self.url = reverse('submit.app')
        self.login('regular@mozilla.com')
        return self.post_addon()

    def test_no_version(self):
        app = app_factory()
        eq_(tasks.fetch_icon(app.pk), None)

    def test_no_icons(self):
        path = os.path.join(self.apps_path, 'noicon.webapp')
        iconless_app = self.webapp_from_path(path)
        tasks.fetch_icon(iconless_app.pk,
                         iconless_app.latest_version.all_files[0].pk)
        assert not self.requests_mock.called

    def test_bad_icons(self):
        path = os.path.join(self.apps_path, 'badicon.webapp')
        iconless_app = self.webapp_from_path(path)
        tasks.fetch_icon(iconless_app.pk,
                         iconless_app.latest_version.all_files[0].pk)
        assert not self.requests_mock.called

    def check_icons(self, webapp, file_obj=None):
        manifest = webapp.get_manifest_json(file_obj)
        biggest = max([int(size) for size in manifest['icons']])

        icon_dir = webapp.get_icon_dir()
        for size in mkt.CONTENT_ICON_SIZES:
            if not size <= biggest:
                continue
            icon_path = os.path.join(icon_dir, '%s-%s.png'
                                     % (str(webapp.id), size))
            with open(icon_path, 'r') as img:
                checker = ImageCheck(img)
                assert checker.is_image()
                eq_(checker.img.size, (size, size))

    def test_data_uri(self):
        app_path = os.path.join(self.apps_path, 'dataicon.webapp')
        webapp = self.webapp_from_path(app_path)
        file_obj = webapp.latest_version.all_files[0]

        tasks.fetch_icon(webapp.pk, file_obj.pk)
        eq_(webapp.icon_type, self.content_type)

        self.check_icons(webapp, file_obj)

    def test_hosted_icon(self):
        app_path = os.path.join(self.apps_path, 'mozball.webapp')
        webapp = self.webapp_from_path(app_path)
        file_obj = webapp.latest_version.all_files[0]

        img_path = os.path.join(self.apps_path, 'mozball-128.png')
        with open(img_path, 'r') as content:
            tasks.save_icon(webapp, content.read())
        eq_(webapp.icon_type, self.content_type)

        self.check_icons(webapp, file_obj)

    @mock.patch('mkt.webapps.models.Webapp.get_manifest_json')
    @mock.patch('mkt.developers.tasks._fetch_content')
    @mock.patch('mkt.developers.tasks.save_icon')
    def test_cdn_icon(self, save, fetch, json):
        response = mock.Mock()
        response.read.return_value = ''
        webapp = app_factory()
        url = 'http://foo.com/bar'
        json.return_value = {'icons': {'128': url}}
        tasks.fetch_icon(webapp.pk, webapp.latest_version.all_files[0].pk)
        assert url in fetch.call_args[0][0]

    @mock.patch('mkt.webapps.models.Webapp.get_manifest_json')
    @mock.patch('mkt.developers.tasks.SafeUnzip')
    @mock.patch('mkt.developers.tasks.save_icon')
    def test_packaged_icon(self, save, zip, json):
        response = mock.Mock()
        response.read.return_value = ''
        zf = mock.Mock()
        zip.return_value = zf
        webapp = app_factory(is_packaged=True)
        file_obj = webapp.latest_version.all_files[0]
        url = '/path/to/icon.png'
        json.return_value = {'icons': {'128': url}}
        tasks.fetch_icon(webapp.pk, file_obj.pk)
        assert url[1:] in zf.extract_path.call_args[0][0]


class TestRegionEmail(mkt.site.tests.WebappTestCase):

    @mock.patch.object(settings, 'SITE_URL', 'http://omg.org/')
    def test_email_for_one_new_region(self):
        tasks.region_email([self.app.id], [mkt.regions.BRA.id])
        msg = mail.outbox[0]
        eq_(msg.subject, '%s: Brazil region added to the Firefox Marketplace'
            % self.app.name)
        eq_(msg.to, ['steamcube@mozilla.com'])
        dev_url = ('http://omg.org/developers/app/something-something/'
                   'edit#details')
        assert unicode(self.app.name) in msg.body
        assert dev_url in msg.body
        assert ' added a new ' in msg.body
        assert ' for Brazil.' in msg.body
        # TODO: Re-enable this when we bring back Unsubscribe (bug 802379).
        # assert 'Unsubscribe' in msg.body

    @mock.patch.object(settings, 'SITE_URL', 'http://omg.org/')
    def test_email_for_two_new_regions(self):
        tasks.region_email([self.app.id],
                           [mkt.regions.GBR.id, mkt.regions.BRA.id])
        msg = mail.outbox[0]
        eq_(msg.subject, '%s: New regions added to the Firefox Marketplace'
                         % self.app.name)
        eq_(msg.to, ['steamcube@mozilla.com'])
        dev_url = ('http://omg.org/developers/app/something-something/'
                   'edit#details')
        assert unicode(self.app.name) in msg.body
        assert dev_url in msg.body
        assert ' added two new ' in msg.body
        assert ': Brazil and United Kingdom.' in msg.body
        # TODO: Re-enable this when we bring back Unsubscribe (bug 802379).
        # assert 'Unsubscribe' in msg.body

    @mock.patch.object(settings, 'SITE_URL', 'http://omg.org/')
    def test_email_for_several_new_regions(self):
        tasks.region_email([self.app.id],
                           [mkt.regions.GBR.id, mkt.regions.USA.id,
                            mkt.regions.BRA.id])
        msg = mail.outbox[0]
        eq_(msg.subject,
            '%s: New regions added to the Firefox Marketplace' % self.app.name)
        assert ' added a few new ' in msg.body
        assert ': Brazil, United Kingdom, and United States.' in msg.body


class TestRegionExclude(mkt.site.tests.WebappTestCase):

    def test_exclude_no_apps(self):
        tasks.region_exclude([], [])
        eq_(AER.objects.count(), 0)

        tasks.region_exclude([], [mkt.regions.GBR.id])
        eq_(AER.objects.count(), 0)

    def test_exclude_no_regions(self):
        tasks.region_exclude([self.app.id], [])
        eq_(AER.objects.count(), 0)

    def test_exclude_one_new_region(self):
        tasks.region_exclude([self.app.id], [mkt.regions.GBR.id])
        excluded = list(AER.objects.filter(addon=self.app)
                        .values_list('region', flat=True))
        eq_(excluded, [mkt.regions.GBR.id])

    def test_exclude_several_new_regions(self):
        tasks.region_exclude([self.app.id], [mkt.regions.USA.id,
                                             mkt.regions.GBR.id])
        excluded = sorted(AER.objects.filter(addon=self.app)
                          .values_list('region', flat=True))
        eq_(excluded, sorted([mkt.regions.USA.id, mkt.regions.GBR.id]))
