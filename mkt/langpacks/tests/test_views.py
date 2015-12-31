# -*- coding: utf-8 -*-
import hashlib
import json
import uuid

from django.conf import settings
from django.core.urlresolvers import reverse
from django.forms import ValidationError
from django.test.utils import override_settings

from dateutil.tz import tzutc
from mock import patch
from nose.tools import eq_, ok_

from lib.crypto.packaged import SigningError
from mkt.api.tests.test_oauth import RestOAuth
from mkt.constants import MANIFEST_CONTENT_TYPE
from mkt.files.models import FileUpload
from mkt.langpacks.models import LangPack
from mkt.langpacks.tests.test_models import UploadCreationMixin, UploadTest
from mkt.site.storage_utils import public_storage
from mkt.site.fixtures import fixture
from mkt.site.tests import TestCase
from mkt.users.models import UserProfile


class TestLangPackViewSetMixin(RestOAuth):
    fixtures = fixture('user_2519')

    def setUp(self):
        super(TestLangPackViewSetMixin, self).setUp()
        self.list_url = reverse('api-v2:langpack-list')
        self.user = UserProfile.objects.get(pk=2519)

    def create_langpack(self, **kwargs):
        data = {
            'active': True,
            'version': '0.1',
            'language': 'fr',
            'fxos_version': '2.2',
        }
        data.update(kwargs)
        return LangPack.objects.create(**data)

    def check_langpack(self, langpack_data, instance=None):
        if instance is None:
            instance = self.langpack
        eq_(instance.pk, langpack_data['uuid'])
        eq_(instance.manifest_url, langpack_data['manifest_url'])
        eq_(instance.active, langpack_data['active'])
        eq_(instance.language, langpack_data['language'])
        eq_(instance.fxos_version, langpack_data['fxos_version'])
        eq_(instance.get_language_display(), langpack_data['language_display'])


class TestLangPackViewSetBase(TestLangPackViewSetMixin):
    def setUp(self):
        super(TestLangPackViewSetBase, self).setUp()
        self.detail_url = reverse('api-v2:langpack-detail', kwargs={'pk': 42})

    def test_cors(self):
        self.assertCORS(self.anon.options(self.detail_url),
                        'get', 'delete', 'patch', 'post', 'put')
        self.assertCORS(self.anon.options(self.list_url),
                        'get', 'delete', 'patch', 'post', 'put')

    def test_no_double_slash(self):
        ok_(not self.detail_url.endswith('//'))
        ok_(not self.list_url.endswith('//'))


class TestLangPackViewSetGet(TestLangPackViewSetMixin):
    def setUp(self):
        super(TestLangPackViewSetGet, self).setUp()
        self.langpack = self.create_langpack()
        self.detail_url = reverse('api-v2:langpack-detail',
                                  kwargs={'pk': self.langpack.pk})

    # Anonymously, you can view all active langpacks.
    # Logged in view the right permission ('LangPacks', '%') you get them
    # all if you use active=0.

    def test_list_active_anonymous(self):
        response = self.anon.get(self.list_url)
        eq_(response.status_code, 200)
        eq_(len(response.json['objects']), 1)
        self.check_langpack(response.json['objects'][0])

    def test_list_active_no_perm_needed(self):
        response = self.client.get(self.list_url)
        eq_(response.status_code, 200)
        eq_(len(response.json['objects']), 1)
        self.check_langpack(response.json['objects'][0])

    def test_list_inactive_anon(self):
        self.create_langpack(active=False)
        response = self.anon.get(self.list_url, {'active': 'false'})
        eq_(response.status_code, 403)

        response = self.anon.get(
            self.list_url, {'active': 'false', 'fxos_version': '2.2'})
        eq_(response.status_code, 403)

    def test_list_inactive_no_perm(self):
        self.create_langpack(active=False)
        response = self.client.get(self.list_url, {'active': 'false'})
        eq_(response.status_code, 403)

        response = self.client.get(
            self.list_url, {'active': 'false', 'fxos_version': '2.2'})
        eq_(response.status_code, 403)

    def test_list_inactive_has_perm(self):
        inactive_langpack = self.create_langpack(active=False)
        self.grant_permission(self.user, 'LangPacks:Admin')
        response = self.client.get(self.list_url, {'active': 'false'})
        eq_(response.status_code, 200)
        eq_(len(response.json['objects']), 1)
        self.check_langpack(response.json['objects'][0],
                            instance=inactive_langpack)

    def test_list_inactive_has_perm_with_fxos_version(self):
        inactive_langpack = self.create_langpack(
            active=False, language='it', fxos_version='3.0')
        self.create_langpack(
            active=False, language='de', fxos_version='2.2')
        self.grant_permission(self.user, 'LangPacks:Admin')
        response = self.client.get(
            self.list_url, {'active': 'false', 'fxos_version': '3.0'})
        eq_(response.status_code, 200)
        eq_(len(response.json['objects']), 1)
        self.check_langpack(response.json['objects'][0],
                            instance=inactive_langpack)

    def test_list_all_has_perm(self):
        inactive_langpack = self.create_langpack(
            active=False, language='it', fxos_version='3.0')
        inactive_langpack.update(created=self.days_ago(1))
        self.grant_permission(self.user, 'LangPacks:Admin')
        response = self.client.get(self.list_url, {'active': 'null'})
        eq_(response.status_code, 200)
        eq_(len(response.json['objects']), 2)
        self.check_langpack(response.json['objects'][0],
                            instance=self.langpack)
        self.check_langpack(response.json['objects'][1],
                            instance=inactive_langpack)

    def test_list_fxos_version(self):
        self.create_langpack(active=True, language='it', fxos_version='3.0')
        response = self.client.get(self.list_url, {'fxos_version': '2.2'})
        eq_(response.status_code, 200)
        eq_(len(response.json['objects']), 1)
        self.check_langpack(response.json['objects'][0],
                            instance=self.langpack)

        response = self.anon.get(self.list_url, {'fxos_version': '2.2'})
        eq_(response.status_code, 200)
        eq_(len(response.json['objects']), 1)
        self.check_langpack(response.json['objects'][0],
                            instance=self.langpack)

    def test_active_detail(self):
        response = self.anon.get(self.detail_url)
        eq_(response.status_code, 200)
        self.check_langpack(response.json)

        response = self.client.get(self.detail_url)
        eq_(response.status_code, 200)
        self.check_langpack(response.json)

    def test_inactive_detail_anon(self):
        self.langpack.update(active=False)
        response = self.anon.get(self.detail_url)
        eq_(response.status_code, 403)

    def test_inactive_detail_no_perm(self):
        self.langpack.update(active=False)
        response = self.client.get(self.detail_url)
        eq_(response.status_code, 403)

    def test_inactive_has_perm(self):
        self.langpack.update(active=False)
        self.grant_permission(self.user, 'LangPacks:Admin')

        response = self.client.get(self.detail_url)
        eq_(response.status_code, 200)
        self.check_langpack(response.json)


class TestLangPackViewSetCreate(TestLangPackViewSetMixin,
                                UploadCreationMixin, UploadTest):
    def test_anonymous(self):
        response = self.anon.post(self.list_url)
        eq_(response.status_code, 403)

    def test_no_perms(self):
        response = self.client.post(self.list_url)
        eq_(response.status_code, 403)

    @patch('mkt.langpacks.serializers.LangPackUploadSerializer.is_valid',
           return_value=True)
    @patch('mkt.langpacks.serializers.LangPackUploadSerializer.save',
           return_value=None)
    def test_with_perm(self, mock_save, mock_is_valid):
        self.grant_permission(self.user, 'LangPacks:Admin')

        response = self.client.post(self.list_url)
        eq_(response.status_code, 201)

    def test_no_upload(self):
        self.grant_permission(self.user, 'LangPacks:Admin')

        response = self.client.post(self.list_url)
        eq_(response.status_code, 400)
        eq_(response.json, {u'upload': [u'This field is required.']})

    def test_upload_does_not_exist(self):
        self.grant_permission(self.user, 'LangPacks:Admin')

        response = self.client.post(self.list_url, data=json.dumps({
            'upload': 'my-non-existing-uuid'}))
        eq_(response.status_code, 400)
        eq_(response.json, {u'upload': [u'No upload found.']})

    def test_dont_own_the_upload(self):
        myid = uuid.uuid4().hex
        FileUpload.objects.create(uuid=myid, user=None, valid=True)
        self.grant_permission(self.user, 'LangPacks:Admin')

        response = self.client.post(self.list_url, data=json.dumps({
            'upload': myid}))
        eq_(response.status_code, 400)
        eq_(response.json, {u'upload': [u'No upload found.']})

    def test_invalid_upload(self):
        myid = uuid.uuid4().hex
        FileUpload.objects.create(uuid=myid, valid=False, user=self.user)
        self.grant_permission(self.user, 'LangPacks:Admin')

        response = self.client.post(self.list_url, data=json.dumps({
            'upload': myid}))
        eq_(response.status_code, 400)
        eq_(response.json, {u'upload': [u'Upload not valid.']})

    @patch('mkt.langpacks.models.LangPack.from_upload')
    def test_errors_returned_by_from_upload(self, mock_from_upload):
        mock_from_upload.side_effect = ValidationError('foo bar')
        myid = uuid.uuid4().hex
        FileUpload.objects.create(uuid=myid, valid=True, user=self.user)
        self.grant_permission(self.user, 'LangPacks:Admin')

        response = self.client.post(self.list_url, data=json.dumps({
            'upload': myid}))
        eq_(response.status_code, 400)
        eq_(response.json, {u'detail': [u'foo bar']})

    @patch('mkt.langpacks.models.sign_app')
    def test_signing_error(self, sign_app_mock):
        sign_app_mock.side_effect = SigningError(u'Fake signing error')
        upload = self.upload('langpack.zip', valid=True, user=self.user)
        self.grant_permission(self.user, 'LangPacks:Admin')

        response = self.client.post(self.list_url, data=json.dumps({
            'upload': upload.uuid}))
        eq_(response.status_code, 503)
        eq_(response.json, {u'detail': [u'Fake signing error']})

    def test_create(self):
        eq_(LangPack.objects.count(), 0)
        upload = self.upload('langpack.zip', valid=True, user=self.user)
        self.grant_permission(self.user, 'LangPacks:Admin')

        response = self.client.post(self.list_url, data=json.dumps({
            'upload': upload.uuid}))
        eq_(response.status_code, 201)
        eq_(LangPack.objects.count(), 1)
        langpack = LangPack.objects.get()
        eq_(langpack.active, False)
        eq_(response.data['uuid'], langpack.uuid)
        eq_(response.data['active'], langpack.active)

    def test_create_with_existing_langpack_in_db(self):
        self.langpack = self.create_langpack()
        eq_(LangPack.objects.count(), 1)
        upload = self.upload('langpack.zip', valid=True, user=self.user)
        self.grant_permission(self.user, 'LangPacks:Admin')

        response = self.client.post(self.list_url, data=json.dumps({
            'upload': upload.uuid}))
        eq_(response.status_code, 201)
        ok_(response.json['uuid'] != self.langpack.pk)
        eq_(LangPack.objects.count(), 2)
        langpack = LangPack.objects.get(pk=response.json['uuid'])
        eq_(langpack.active, False)
        eq_(langpack.language, 'de')
        eq_(langpack.fxos_version, '2.2')
        eq_(response.data['uuid'], langpack.uuid)
        eq_(response.data['active'], langpack.active)


class TestLangPackViewSetUpdate(TestLangPackViewSetMixin, UploadCreationMixin,
                                UploadTest):
    def setUp(self):
        super(TestLangPackViewSetUpdate, self).setUp()
        self.langpack = self.create_langpack()
        self.detail_url = reverse('api-v2:langpack-detail',
                                  kwargs={'pk': self.langpack.pk})

    def test_anonymous(self):
        response = self.anon.put(self.detail_url)
        eq_(response.status_code, 403)

    def test_no_perms(self):
        response = self.client.put(self.detail_url)
        eq_(response.status_code, 403)

    @patch('mkt.langpacks.serializers.LangPackUploadSerializer.is_valid',
           return_value=True)
    @patch('mkt.langpacks.serializers.LangPackUploadSerializer.save',
           return_value=None)
    def test_with_perm(self, mock_save, mock_is_valid):
        self.grant_permission(self.user, 'LangPacks:Admin')

        response = self.client.put(self.detail_url)
        eq_(response.status_code, 200)

    def test_no_upload(self):
        self.grant_permission(self.user, 'LangPacks:Admin')

        response = self.client.put(self.detail_url)
        eq_(response.status_code, 400)
        eq_(response.json, {u'upload': [u'This field is required.']})

    def test_upload_does_not_exist(self):
        self.grant_permission(self.user, 'LangPacks:Admin')

        response = self.client.put(self.detail_url, data=json.dumps({
            'upload': 'my-non-existing-uuid'}))
        eq_(response.status_code, 400)
        eq_(response.json, {u'upload': [u'No upload found.']})

    def test_dont_own_the_upload(self):
        myid = uuid.uuid4().hex
        FileUpload.objects.create(uuid=myid, user=None, valid=True)
        self.grant_permission(self.user, 'LangPacks:Admin')

        response = self.client.put(self.detail_url, data=json.dumps({
            'upload': myid}))
        eq_(response.status_code, 400)
        eq_(response.json, {u'upload': [u'No upload found.']})

    def test_invalid_upload(self):
        myid = uuid.uuid4().hex
        FileUpload.objects.create(uuid=myid, valid=False, user=self.user)
        self.grant_permission(self.user, 'LangPacks:Admin')

        response = self.client.put(self.detail_url, data=json.dumps({
            'upload': myid}))
        eq_(response.status_code, 400)
        eq_(response.json, {u'upload': [u'Upload not valid.']})

    @patch('mkt.langpacks.models.LangPack.from_upload')
    def test_errors_returned_by_from_upload(self, mock_from_upload):
        mock_from_upload.side_effect = ValidationError('foo bar')
        myid = uuid.uuid4().hex
        FileUpload.objects.create(uuid=myid, valid=True, user=self.user)
        self.grant_permission(self.user, 'LangPacks:Admin')

        response = self.client.put(self.detail_url, data=json.dumps({
            'upload': myid}))
        eq_(response.status_code, 400)
        eq_(response.json, {u'detail': [u'foo bar']})

    def test_update(self):
        upload = self.upload('langpack.zip', valid=True, user=self.user)
        self.grant_permission(self.user, 'LangPacks:Admin')

        response = self.client.put(self.detail_url, data=json.dumps({
            'upload': upload.uuid}))
        eq_(response.status_code, 200)
        eq_(LangPack.objects.count(), 1)
        langpack = LangPack.objects.get()
        eq_(langpack.active, True)  # Langpack was already active.
        eq_(langpack.language, 'de')
        eq_(langpack.fxos_version, '2.2')
        eq_(response.data['uuid'], langpack.uuid)
        eq_(response.data['active'], langpack.active)

    def test_update_with_another_existing_langpack_in_db(self):
        self.langpack = self.create_langpack()
        eq_(LangPack.objects.count(), 2)
        upload = self.upload('langpack.zip', valid=True, user=self.user)
        self.grant_permission(self.user, 'LangPacks:Admin')

        response = self.client.put(self.detail_url, data=json.dumps({
            'upload': upload.uuid}))
        eq_(response.status_code, 200)
        eq_(LangPack.objects.count(), 2)
        langpack = LangPack.objects.get(pk=response.json['uuid'])
        eq_(langpack.active, True)
        eq_(langpack.language, 'de')
        eq_(langpack.fxos_version, '2.2')
        eq_(response.data['uuid'], langpack.uuid)
        eq_(response.data['active'], langpack.active)

    def test_update_was_inactive(self):
        self.langpack.update(active=False)
        upload = self.upload('langpack.zip', valid=True, user=self.user)
        self.grant_permission(self.user, 'LangPacks:Admin')

        response = self.client.put(self.detail_url, data=json.dumps({
            'upload': upload.uuid}))
        eq_(response.status_code, 200)
        eq_(LangPack.objects.count(), 1)
        langpack = LangPack.objects.get()
        eq_(langpack.active, False)
        eq_(langpack.language, 'de')
        eq_(langpack.fxos_version, '2.2')
        eq_(response.data['uuid'], langpack.uuid)
        eq_(response.data['active'], langpack.active)


class TestLangPackViewSetPartialUpdate(TestLangPackViewSetMixin):
    def setUp(self):
        super(TestLangPackViewSetPartialUpdate, self).setUp()
        self.langpack = self.create_langpack()
        self.detail_url = reverse('api-v2:langpack-detail',
                                  kwargs={'pk': self.langpack.pk})

    def test_anonymous(self):
        response = self.anon.patch(self.detail_url)
        eq_(response.status_code, 403)

    def test_no_perms(self):
        response = self.client.patch(self.detail_url)
        eq_(response.status_code, 403)

    def test_with_perm(self):
        self.grant_permission(self.user, 'LangPacks:Admin')

        response = self.client.patch(self.detail_url,
                                     json.dumps({'active': False}))
        eq_(response.status_code, 200)
        eq_(response.data['active'], False)
        self.langpack.reload()
        eq_(self.langpack.pk, response.data['uuid'])
        eq_(self.langpack.active, response.data['active'])

    def test_not_allowed_fields(self):
        self.grant_permission(self.user, 'LangPacks:Admin')
        original_filename = self.langpack.filename

        response = self.client.patch(self.detail_url, json.dumps({
            'active': False,
            'filename': 'dummy-data',
            'fxos_version': 'dummy-data',
            'language': 'es',
            'modified': 'dummy-data',
            'uuid': 'dummy-data',
            'version': 'dummy-data',
        }))
        eq_(response.status_code, 400)
        eq_(response.data, {
            'language': [u'This field is read-only.'],
            'fxos_version': [u'This field is read-only.'],
            'version': [u'This field is read-only.']})
        self.langpack.reload()
        # Verify that nothing has changed.
        eq_(self.langpack.active, True)
        # Not changed either (not even exposed, so does not trigger an error)
        eq_(self.langpack.filename, original_filename)


class TestLangPackViewSetDelete(TestLangPackViewSetMixin):
    def setUp(self):
        super(TestLangPackViewSetDelete, self).setUp()
        self.langpack = self.create_langpack()
        self.detail_url = reverse('api-v2:langpack-detail',
                                  kwargs={'pk': self.langpack.pk})

    def test_anonymous(self):
        response = self.anon.delete(self.detail_url)
        eq_(response.status_code, 403)

    def test_no_perms(self):
        response = self.client.delete(self.detail_url)
        eq_(response.status_code, 403)

    def test_with_perm(self):
        self.grant_permission(self.user, 'LangPacks:Admin')
        langpack_to_keep = self.create_langpack()
        eq_(LangPack.objects.count(), 2)

        response = self.client.delete(self.detail_url)
        eq_(response.status_code, 204)
        eq_(LangPack.objects.count(), 1)
        eq_(LangPack.objects.get().pk, langpack_to_keep.pk)


class TestLangPackNonAPIViews(TestCase):
    fixtures = fixture('user_2519')

    def setUp(self):
        super(TestLangPackNonAPIViews, self).setUp()
        self.fake_manifest = {
            'name': u'Fake LangPäck',
            'developer': {
                'name': 'Mozilla'
            }
        }
        self.langpack = LangPack.objects.create(
            version='0.1', active=True,
            manifest=json.dumps(self.fake_manifest))
        self.user = UserProfile.objects.get(pk=2519)
        with public_storage.open(self.langpack.file_path, 'w') as f:
            f.write('sample data\n')

    def _expected_etag(self):
        expected_etag = hashlib.sha256()
        expected_etag.update(unicode(self.langpack.pk))
        expected_etag.update(unicode(self.langpack.file_version))
        return '"%s"' % expected_etag.hexdigest()

    @override_settings(
        XSENDFILE=True,
        DEFAULT_FILE_STORAGE='mkt.site.storage_utils.LocalFileStorage')
    def test_download(self):
        ok_(self.langpack.download_url)
        response = self.client.get(self.langpack.download_url)

        eq_(response.status_code, 200)
        eq_(response[settings.XSENDFILE_HEADER], self.langpack.file_path)
        eq_(response['Content-Type'], 'application/zip')
        eq_(response['etag'], self._expected_etag())

        self.login(self.user)
        response = self.client.get(self.langpack.download_url)
        eq_(response.status_code, 200)

    @override_settings(
        DEFAULT_FILE_STORAGE='mkt.site.storage_utils.S3BotoPrivateStorage')
    def test_download_storage(self):
        ok_(self.langpack.download_url)
        response = self.client.get(self.langpack.download_url)
        path = public_storage.url(self.langpack.file_path)
        self.assert3xx(response, path)

    def test_download_inactive(self):
        self.langpack.update(active=False)
        ok_(self.langpack.download_url)
        response = self.client.get(self.langpack.download_url)
        eq_(response.status_code, 404)

        self.login(self.user)
        response = self.client.get(self.langpack.download_url)
        eq_(response.status_code, 404)

    @override_settings(
        XSENDFILE=True,
        DEFAULT_FILE_STORAGE='mkt.site.storage_utils.LocalFileStorage')
    def test_download_inactive_has_perm(self):
        self.langpack.update(active=False)
        self.grant_permission(self.user, 'LangPacks:Admin')
        self.login(self.user)
        ok_(self.langpack.download_url)
        response = self.client.get(self.langpack.download_url)
        eq_(response.status_code, 200)
        eq_(response[settings.XSENDFILE_HEADER], self.langpack.file_path)
        eq_(response['Content-Type'], 'application/zip')
        eq_(response['etag'], self._expected_etag())

    def test_manifest(self):
        ok_(self.langpack.manifest_url)
        response = self.client.get(self.langpack.manifest_url)
        eq_(response.status_code, 200)
        eq_(response['Content-Type'], MANIFEST_CONTENT_TYPE)
        manifest_contents = json.loads(
            self.langpack.get_minifest_contents()[0])
        data = json.loads(response.content)
        eq_(data, manifest_contents)

    def test_manifest_etag(self):
        response = self.client.get(self.langpack.manifest_url)
        eq_(response.status_code, 200)
        original_etag = response['ETag']
        ok_(original_etag)
        self.assertCloseToNow(
            response['Last-Modified'],
            now=self.langpack.modified.replace(tzinfo=tzutc()))

        # Test that the etag is different if the langpack file_version changes.
        self.langpack.update(file_version=42)
        self.langpack.get_minifest_contents(force=True)  # Re-generate cache.
        response = self.client.get(self.langpack.manifest_url)
        eq_(response.status_code, 200)
        new_etag = response['ETag']
        ok_(new_etag)
        ok_(original_etag != new_etag)

        # Test that the etag is different if just the minifest contents change,
        # but not the langpack instance itself.
        minifest_contents = json.loads(
            self.langpack.get_minifest_contents()[0])
        minifest_contents['name'] = 'Different Name'
        minifest_contents = json.dumps(minifest_contents)
        patch_method = 'mkt.langpacks.models.LangPack.get_minifest_contents'
        with patch(patch_method) as get_minifest_contents_mock:
            get_minifest_contents_mock.return_value = (
                minifest_contents, 'yet_another_etag')
            response = self.client.get(self.langpack.manifest_url)
            eq_(response.status_code, 200)
            yet_another_etag = response['ETag']
            ok_(yet_another_etag)
            ok_(original_etag != new_etag != yet_another_etag)

    def test_manifest_inactive(self):
        manifest_url = self.langpack.manifest_url
        ok_(manifest_url)
        self.langpack.update(active=False)
        # We don't return a manifest url when the langpack is inactive.
        eq_(self.langpack.manifest_url, '')
        response = self.client.get(manifest_url)
        eq_(response.status_code, 404)

    def test_manifest_inactive_has_perm(self):
        manifest_url = self.langpack.manifest_url
        ok_(manifest_url)
        self.langpack.update(active=False)
        self.grant_permission(self.user, 'LangPacks:Admin')
        self.login(self.user)
        # We don't return a manifest url when the langpack is inactive, but
        # it should still work if you have the right permission.
        eq_(self.langpack.manifest_url, '')
        response = self.client.get(manifest_url)
        eq_(response.status_code, 200)
        manifest_contents = json.loads(
            self.langpack.get_minifest_contents()[0])
        data = json.loads(response.content)
        eq_(data, manifest_contents)
