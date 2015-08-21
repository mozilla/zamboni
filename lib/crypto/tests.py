# -*- coding: utf-8 -*-
import json
import shutil
import zipfile

from django.conf import settings  # For mocking.

import jwt
import mock
from nose.tools import eq_, raises
from requests import Timeout

import mkt.site.tests
from lib.crypto import packaged
from lib.crypto.receipt import crack, sign, SigningError
from mkt.site.storage_utils import copy_to_storage
from mkt.site.fixtures import fixture
from mkt.site.storage_utils import public_storage, private_storage
from mkt.versions.models import Version
from mkt.webapps.models import Webapp


def mock_sign(version_id, reviewer=False):
    """
    This is a mock for using in tests, where we really don't want to be
    actually signing the apps. This just copies the file over and returns
    the path. It doesn't have much error checking.
    """
    version = Version.objects.get(pk=version_id)
    file_obj = version.all_files[0]
    path = (file_obj.signed_reviewer_file_path if reviewer else
            file_obj.signed_file_path)
    with private_storage.open(path, 'w') as dest_f:
        shutil.copyfileobj(private_storage.open(file_obj.file_path), dest_f)
    return path


@mock.patch('lib.crypto.receipt.requests.post')
@mock.patch.object(settings, 'SIGNING_SERVER', 'http://localhost')
class TestReceipt(mkt.site.tests.TestCase):

    def test_called(self, get):
        get.return_value = self.get_response(200)
        sign('my-receipt')
        eq_(get.call_args[1]['data'], 'my-receipt')

    def test_some_unicode(self, get):
        get.return_value = self.get_response(200)
        sign({'name': u'Вагиф Сәмәдоғлу'})

    def get_response(self, code):
        return mock.Mock(status_code=code,
                         content=json.dumps({'receipt': ''}))

    def test_good(self, req):
        req.return_value = self.get_response(200)
        sign('x')

    @raises(SigningError)
    def test_timeout(self, req):
        req.side_effect = Timeout
        req.return_value = self.get_response(200)
        sign('x')

    @raises(SigningError)
    def test_error(self, req):
        req.return_value = self.get_response(403)
        sign('x')

    @raises(SigningError)
    def test_other(self, req):
        req.return_value = self.get_response(206)
        sign('x')


class TestCrack(mkt.site.tests.TestCase):

    def test_crack(self):
        eq_(crack(jwt.encode('foo', 'x')), [u'foo'])

    def test_crack_mulitple(self):
        eq_(crack('~'.join([jwt.encode('foo', 'x'), jwt.encode('bar', 'y')])),
            [u'foo', u'bar'])


class PackagedApp(mkt.site.tests.TestCase, mkt.site.tests.MktPaths):
    fixtures = fixture('webapp_337141', 'users')

    def setUp(self):
        self.app = Webapp.objects.get(pk=337141)
        self.app.update(is_packaged=True)
        self.version = self.app.current_version
        self.file = self.version.all_files[0]
        self.file.update(filename='mozball.zip')

    def setup_files(self):
        # Clean out any left over stuff.
        public_storage.delete(self.file.signed_file_path)
        private_storage.delete(self.file.signed_reviewer_file_path)

        # Make sure the source file is there.
        if not private_storage.exists(self.file.file_path):
            copy_to_storage(self.packaged_app_path('mozball.zip'),
                            self.file.file_path)


@mock.patch('lib.crypto.packaged.os.unlink', new=mock.Mock)
class TestPackaged(PackagedApp, mkt.site.tests.TestCase):

    def setUp(self):
        super(TestPackaged, self).setUp()
        self.setup_files()

    @raises(packaged.SigningError)
    def test_not_packaged(self):
        self.app.update(is_packaged=False)
        packaged.sign(self.version.pk)

    @raises(packaged.SigningError)
    def test_no_file(self):
        [f.delete() for f in self.app.current_version.all_files]
        packaged.sign(self.version.pk)

    @mock.patch('lib.crypto.packaged.sign_app')
    def test_already_exists(self, sign_app):
        with public_storage.open(self.file.signed_file_path, 'w') as f:
            f.write('.')
        assert packaged.sign(self.version.pk)
        assert not sign_app.called

    @mock.patch('lib.crypto.packaged.sign_app')
    def test_resign_already_exists(self, sign_app):
        private_storage.open(self.file.signed_file_path, 'w')
        packaged.sign(self.version.pk, resign=True)
        assert sign_app.called

    @mock.patch('lib.crypto.packaged.sign_app')
    def test_sign_consumer(self, sign_app):
        packaged.sign(self.version.pk)
        assert sign_app.called
        ids = json.loads(sign_app.call_args[0][2])
        eq_(ids['id'], self.app.guid)
        eq_(ids['version'], self.version.pk)

    @mock.patch('lib.crypto.packaged.sign_app')
    def test_sign_reviewer(self, sign_app):
        packaged.sign(self.version.pk, reviewer=True)
        assert sign_app.called
        ids = json.loads(sign_app.call_args[0][2])
        eq_(ids['id'], 'reviewer-{guid}-{version_id}'.format(
            guid=self.app.guid, version_id=self.version.pk))
        eq_(ids['version'], self.version.pk)

    @raises(ValueError)
    def test_server_active(self):
        with self.settings(SIGNED_APPS_SERVER_ACTIVE=True):
            packaged.sign(self.version.pk)

    @raises(ValueError)
    def test_reviewer_server_active(self):
        with self.settings(SIGNED_APPS_REVIEWER_SERVER_ACTIVE=True):
            packaged.sign(self.version.pk, reviewer=True)

    @mock.patch('lib.crypto.packaged._no_sign')
    def test_server_inactive(self, _no_sign):
        with self.settings(SIGNED_APPS_SERVER_ACTIVE=False):
            packaged.sign(self.version.pk)
        assert _no_sign.called

    @mock.patch('lib.crypto.packaged._no_sign')
    def test_reviewer_server_inactive(self, _no_sign):
        with self.settings(SIGNED_APPS_REVIEWER_SERVER_ACTIVE=False):
            packaged.sign(self.version.pk, reviewer=True)
        assert _no_sign.called

    def test_server_endpoint(self):
        with self.settings(SIGNED_APPS_SERVER_ACTIVE=True,
                           SIGNED_APPS_SERVER='http://sign.me',
                           SIGNED_APPS_REVIEWER_SERVER='http://review.me'):
            endpoint = packaged._get_endpoint()
        assert endpoint.startswith('http://sign.me'), (
            'Unexpected endpoint returned.')

    def test_server_reviewer_endpoint(self):
        with self.settings(SIGNED_APPS_REVIEWER_SERVER_ACTIVE=True,
                           SIGNED_APPS_SERVER='http://sign.me',
                           SIGNED_APPS_REVIEWER_SERVER='http://review.me'):
            endpoint = packaged._get_endpoint(reviewer=True)
        assert endpoint.startswith('http://review.me'), (
            'Unexpected endpoint returned.')

    @mock.patch.object(packaged, '_get_endpoint', lambda _: '/fake/url/')
    @mock.patch('requests.post')
    def test_inject_ids(self, post):
        post().status_code = 200
        post().content = '{"zigbert.rsa": ""}'
        packaged.sign(self.version.pk)
        zf = zipfile.ZipFile(public_storage.open(self.file.signed_file_path),
                             mode='r')
        ids_data = zf.read('META-INF/ids.json')
        eq_(sorted(json.loads(ids_data).keys()), ['id', 'version'])
