# -*- coding: utf-8 -*-
import json

from django.core.urlresolvers import reverse
from django.forms import ValidationError

from mock import patch
from nose.tools import eq_

from mkt.api.tests.test_oauth import RestOAuth
from mkt.files.models import FileUpload
from mkt.langpacks.models import LangPack
from mkt.langpacks.tests.test_models import UploadCreationMixin, UploadTest
from mkt.site.fixtures import fixture
from mkt.users.models import UserProfile


class TestLangPackViewSet(RestOAuth):
    fixtures = fixture('user_2519')

    def setUp(self):
        super(TestLangPackViewSet, self).setUp()
        self.url = reverse('api-v2:langpack-list')
        self.detail_url = reverse('api-v2:langpack-detail', kwargs={'pk': 42})
        self.user = UserProfile.objects.get(pk=2519)

    def test_cors(self):
        self.assertCORS(self.anon.options(self.detail_url),
                        'get', 'delete', 'patch', 'post', 'put')
        self.assertCORS(self.anon.options(self.url),
                        'get', 'delete', 'patch', 'post', 'put')


class TestLangPackViewSetCreate(RestOAuth, UploadCreationMixin, UploadTest):
    fixtures = fixture('user_2519')

    def setUp(self):
        super(TestLangPackViewSetCreate, self).setUp()
        self.url = reverse('api-v2:langpack-list')
        self.user = UserProfile.objects.get(pk=2519)

    def test_anonymous(self):
        response = self.anon.post(self.url)
        eq_(response.status_code, 403)

    def test_no_perms(self):
        response = self.client.post(self.url)
        eq_(response.status_code, 403)

    @patch('mkt.langpacks.serializers.LangPackUploadSerializer.is_valid',
           return_value=True)
    @patch('mkt.langpacks.serializers.LangPackUploadSerializer.save',
           return_value=None)
    def test_with_perm(self, mock_save, mock_is_valid):
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.post(self.url)
        eq_(response.status_code, 201)

    def test_no_upload(self):
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.post(self.url)
        eq_(response.status_code, 400)
        eq_(response.json, {u'upload': [u'This field is required.']})

    def test_upload_does_not_exist(self):
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.post(self.url, data=json.dumps({
            'upload': 'my-non-existing-uuid'}))
        eq_(response.status_code, 400)
        eq_(response.json, {u'upload': [u'No upload found.']})

    def test_dont_own_the_upload(self):
        FileUpload.objects.create(uuid='my-uuid', user=None, valid=True)
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.post(self.url, data=json.dumps({
            'upload': 'my-uuid'}))
        eq_(response.status_code, 400)
        eq_(response.json, {u'upload': [u'No upload found.']})

    def test_invalid_upload(self):
        FileUpload.objects.create(uuid='my-uuid', valid=False, user=self.user)
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.post(self.url, data=json.dumps({
            'upload': 'my-uuid'}))
        eq_(response.status_code, 400)
        eq_(response.json, {u'upload': [u'Upload not valid.']})

    @patch('mkt.langpacks.models.LangPack.from_upload')
    def test_errors_returned_by_from_upload(self, mock_from_upload):
        mock_from_upload.side_effect = ValidationError('foo bar')
        FileUpload.objects.create(uuid='my-uuid', valid=True, user=self.user)
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.post(self.url, data=json.dumps({
            'upload': 'my-uuid'}))
        eq_(response.status_code, 400)
        eq_(response.json, {u'detail': [u'foo bar']})

    def test_everything_is_fine(self):
        eq_(LangPack.objects.count(), 0)
        upload = self.upload('langpack.zip', valid=True, user=self.user)
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.post(self.url, data=json.dumps({
            'upload': upload.uuid}))
        eq_(response.status_code, 201)
        eq_(LangPack.objects.count(), 1)
        langpack = LangPack.objects.get()
        eq_(langpack.hash[0:23], 'sha256:f0fa5a4f5c0edf2d')
        eq_(langpack.size, 499)
        eq_(langpack.active, False)
        eq_(response.data['uuid'], langpack.uuid)
        eq_(response.data['hash'], langpack.hash)
        eq_(response.data['active'], langpack.active)


class TestLangPackViewSetUpdate(RestOAuth, UploadCreationMixin, UploadTest):
    fixtures = fixture('user_2519')

    def setUp(self):
        super(TestLangPackViewSetUpdate, self).setUp()
        self.create_langpack()
        self.url = reverse('api-v2:langpack-detail',
                           kwargs={'pk': self.langpack.pk})
        self.user = UserProfile.objects.get(pk=2519)

    def create_langpack(self):
        self.langpack = LangPack.objects.create(
            filename='dummy.zip', active=True, hash='dummy-hash',
            version='0.1', language='fr', fxos_version='2.2')

    def test_anonymous(self):
        response = self.anon.put(self.url)
        eq_(response.status_code, 403)

    def test_no_perms(self):
        response = self.client.put(self.url)
        eq_(response.status_code, 403)

    @patch('mkt.langpacks.serializers.LangPackUploadSerializer.is_valid',
           return_value=True)
    @patch('mkt.langpacks.serializers.LangPackUploadSerializer.save',
           return_value=None)
    def test_with_perm(self, mock_save, mock_is_valid):
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.put(self.url)
        eq_(response.status_code, 200)

    def test_no_upload(self):
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.put(self.url)
        eq_(response.status_code, 400)
        eq_(response.json, {u'upload': [u'This field is required.']})

    def test_upload_does_not_exist(self):
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.put(self.url, data=json.dumps({
            'upload': 'my-non-existing-uuid'}))
        eq_(response.status_code, 400)
        eq_(response.json, {u'upload': [u'No upload found.']})

    def test_dont_own_the_upload(self):
        FileUpload.objects.create(uuid='my-uuid', user=None, valid=True)
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.put(self.url, data=json.dumps({
            'upload': 'my-uuid'}))
        eq_(response.status_code, 400)
        eq_(response.json, {u'upload': [u'No upload found.']})

    def test_invalid_upload(self):
        FileUpload.objects.create(uuid='my-uuid', valid=False, user=self.user)
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.put(self.url, data=json.dumps({
            'upload': 'my-uuid'}))
        eq_(response.status_code, 400)
        eq_(response.json, {u'upload': [u'Upload not valid.']})

    @patch('mkt.langpacks.models.LangPack.from_upload')
    def test_errors_returned_by_from_upload(self, mock_from_upload):
        mock_from_upload.side_effect = ValidationError('foo bar')
        FileUpload.objects.create(uuid='my-uuid', valid=True, user=self.user)
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.put(self.url, data=json.dumps({
            'upload': 'my-uuid'}))
        eq_(response.status_code, 400)
        eq_(response.json, {u'detail': [u'foo bar']})

    def test_everything_is_fine(self):
        upload = self.upload('langpack.zip', valid=True, user=self.user)
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.put(self.url, data=json.dumps({
            'upload': upload.uuid}))
        eq_(response.status_code, 200)
        eq_(LangPack.objects.count(), 1)
        langpack = LangPack.objects.get()
        eq_(langpack.hash[0:23], 'sha256:f0fa5a4f5c0edf2d')
        eq_(langpack.size, 499)
        eq_(langpack.active, True)
        eq_(langpack.language, 'de')
        eq_(langpack.fxos_version, '2.2')
        eq_(response.data['uuid'], langpack.uuid)
        eq_(response.data['hash'], langpack.hash)
        eq_(response.data['active'], langpack.active)

    def test_everything_is_fine_was_inactive(self):
        self.langpack.update(active=False)
        upload = self.upload('langpack.zip', valid=True, user=self.user)
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.put(self.url, data=json.dumps({
            'upload': upload.uuid}))
        eq_(response.status_code, 200)
        eq_(LangPack.objects.count(), 1)
        langpack = LangPack.objects.get()
        eq_(langpack.hash[0:23], 'sha256:f0fa5a4f5c0edf2d')
        eq_(langpack.size, 499)
        eq_(langpack.active, False)
        eq_(langpack.language, 'de')
        eq_(langpack.fxos_version, '2.2')
        eq_(response.data['uuid'], langpack.uuid)
        eq_(response.data['hash'], langpack.hash)
        eq_(response.data['active'], langpack.active)


class TestLangPackViewSetPartialUpdate(RestOAuth):
    fixtures = fixture('user_2519')

    def setUp(self):
        super(TestLangPackViewSetPartialUpdate, self).setUp()
        self.create_langpack()
        self.url = reverse('api-v2:langpack-detail',
                           kwargs={'pk': self.langpack.pk})
        self.user = UserProfile.objects.get(pk=2519)

    def create_langpack(self):
        self.langpack = LangPack.objects.create(
            filename='dummy.zip', active=True, hash='dummy-hash',
            version='0.1', language='fr', fxos_version='2.2')

    def test_anonymous(self):
        response = self.anon.patch(self.url)
        eq_(response.status_code, 403)

    def test_no_perms(self):
        response = self.client.patch(self.url)
        eq_(response.status_code, 403)

    def test_with_perm(self):
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.patch(self.url, json.dumps({'active': False}))
        eq_(response.status_code, 200)
        eq_(response.data['active'], False)
        self.langpack.reload()
        eq_(self.langpack.pk, response.data['uuid'])
        eq_(self.langpack.active, response.data['active'])

    def test_not_allowed_fields(self):
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.patch(self.url, json.dumps({
            'active': False,
            'filename': 'dummy-data',
            'fxos_version': 'dummy-data',
            'hash': 'dummy-data',
            'language': 'es',
            'modified': 'dummy-data',
            'size': 666,
            'uuid': 'dummy-data',
            'version': 'dummy-data',
        }))
        eq_(response.status_code, 400)
        eq_(response.data, {
            'hash': [u'This field is read-only.'],
            'language': [u'This field is read-only.'],
            'fxos_version': [u'This field is read-only.'],
            'filename': [u'This field is read-only.'],
            'version': [u'This field is read-only.'],
            'size': [u'This field is read-only.']})
        self.langpack.reload()
        eq_(self.langpack.active, True)  # Not changed.
