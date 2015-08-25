# -*- coding: utf-8 -*-
import json

from django.core.urlresolvers import reverse

from nose.tools import eq_, ok_

from mkt.api.tests.test_oauth import RestOAuth
from mkt.constants.base import STATUS_PENDING, STATUS_PUBLIC
from mkt.extensions.models import Extension
from mkt.files.models import FileUpload
from mkt.files.tests.test_models import UploadTest
from mkt.site.fixtures import fixture
from mkt.site.storage_utils import private_storage
from mkt.site.tests import ESTestCase, MktPaths
from mkt.users.models import UserProfile


class TestExtensionValidationViewSet(MktPaths, RestOAuth):
    fixtures = fixture('user_2519')

    def setUp(self):
        super(TestExtensionValidationViewSet, self).setUp()
        self.list_url = reverse('api-v2:extension-validation-list')
        self.user = UserProfile.objects.get(pk=2519)

    def _test_create_success(self, client):
        headers = {
            'HTTP_CONTENT_TYPE': 'application/zip',
            'HTTP_CONTENT_DISPOSITION': 'form-data; name="binary_data"; '
                                        'filename="foo.zip"'
        }
        with open(self.packaged_app_path('extension.zip'), 'rb') as fd:
            response = client.post(self.list_url, fd.read(),
                                   content_type='application/zip', **headers)

        eq_(response.status_code, 202)
        data = response.json
        upload = FileUpload.objects.get(pk=data['id'])
        eq_(upload.valid, True)  # We directly set uploads as valid atm.
        eq_(upload.name, 'foo.zip')
        ok_(upload.hash.startswith('sha256:58ef3f15dd423c3ab9b0285ac01e692c5'))
        ok_(upload.path)
        ok_(private_storage.exists(upload.path))
        return upload

    def test_create_anonymous(self):
        upload = self._test_create_success(client=self.anon)
        eq_(upload.user, None)

    def test_create_logged_in(self):
        upload = self._test_create_success(client=self.client)
        eq_(upload.user, self.user)

    def test_create_missing_no_data(self):
        headers = {
            'HTTP_CONTENT_TYPE': 'application/zip',
            'HTTP_CONTENT_DISPOSITION': 'form-data; name="binary_data"; '
                                        'filename="foo.zip"'
        }
        response = self.anon.post(self.list_url,
                                  content_type='application/zip', **headers)
        eq_(response.status_code, 400)

    def test_cors(self):
        response = self.anon.post(self.list_url)
        self.assertCORS(response, 'get', 'post',
                        headers=['Content-Disposition', 'Content-Type'])

    def test_create_missing_content_disposition(self):
        headers = {
            'HTTP_CONTENT_TYPE': 'application/zip',
        }
        with open(self.packaged_app_path('extension.zip'), 'rb') as fd:
            response = self.client.post(
                self.list_url, fd.read(), content_type='application/zip',
                **headers)
        eq_(response.status_code, 400)

    def test_create_wrong_type(self):
        headers = {
            'HTTP_CONTENT_TYPE': 'application/foobar',
            'HTTP_CONTENT_DISPOSITION': 'form-data; name="binary_data"; '
                                        'filename="foo.zip"'
        }
        with open(self.packaged_app_path('extension.zip'), 'rb') as fd:
            response = self.client.post(
                self.list_url, fd.read(), content_type='application/foobar',
                **headers)
        eq_(response.status_code, 400)

    def test_create_invalid_zip(self):
        headers = {
            'HTTP_CONTENT_TYPE': 'application/zip',
            'HTTP_CONTENT_DISPOSITION': 'form-data; name="binary_data"; '
                                        'filename="foo.zip"'
        }
        response = self.client.post(
            self.list_url, 'XXXXXX', content_type='application/zip', **headers)
        eq_(response.status_code, 400)

    def test_create_no_manifest_json(self):
        headers = {
            'HTTP_CONTENT_TYPE': 'application/zip',
            'HTTP_CONTENT_DISPOSITION': 'form-data; name="binary_data"; '
                                        'filename="foo.zip"'
        }
        # mozball.zip is an app, not an extension, it has no manifest.json.
        with open(self.packaged_app_path('mozball.zip'), 'rb') as fd:
            response = self.client.post(
                self.list_url, fd.read(), content_type='application/zip',
                **headers)
        eq_(response.status_code, 400)

    def test_view_result_anonymous(self):
        upload = FileUpload.objects.create(valid=True)
        url = reverse('api-v2:extension-validation-detail',
                      kwargs={'pk': upload.pk})
        response = self.anon.get(url)
        eq_(response.status_code, 200)
        eq_(response.json['valid'], True)


class TestExtensionViewSetPost(UploadTest, RestOAuth):
    fixtures = fixture('user_2519', 'user_999')

    def setUp(self):
        super(TestExtensionViewSetPost, self).setUp()
        self.list_url = reverse('api-v2:extension-list')
        self.user = UserProfile.objects.get(pk=2519)

    def test_create_logged_in(self):
        upload = self.get_upload(
            abspath=self.packaged_app_path('extension.zip'), user=self.user)
        eq_(upload.valid, True)
        response = self.client.post(self.list_url,
                                    json.dumps({'upload': upload.pk}))
        eq_(response.status_code, 201)
        data = response.json
        eq_(data['version'], '0.1')
        eq_(data['name'], {"en-US": u"My Lîttle Extension"})
        eq_(data['status'], 'pending')
        ok_(data['slug'])
        eq_(Extension.objects.count(), 1)
        extension = Extension.objects.get(pk=data['id'])
        eq_(extension.status, STATUS_PENDING)
        eq_(list(extension.authors.all()), [self.user])

    def test_create_upload_has_no_user(self):
        upload = self.get_upload(
            abspath=self.packaged_app_path('extension.zip'), user=None)
        response = self.client.post(self.list_url,
                                    json.dumps({'upload': upload.pk}))
        eq_(response.status_code, 404)

    def test_create_upload_has_wrong_user(self):
        second_user = UserProfile.objects.get(pk=999)
        upload = self.get_upload(
            abspath=self.packaged_app_path('extension.zip'), user=second_user)
        response = self.client.post(self.list_url,
                                    json.dumps({'upload': upload.pk}))
        eq_(response.status_code, 404)

    def test_invalid_pk(self):
        upload = self.get_upload(
            abspath=self.packaged_app_path('extension.zip'), user=self.user)
        eq_(upload.valid, True)
        response = self.client.post(self.list_url,
                                    json.dumps({'upload': upload.pk + 'lol'}))
        eq_(response.status_code, 404)

    def test_not_validated(self):
        upload = self.get_upload(
            abspath=self.packaged_app_path('extension.zip'), user=self.user,
            validation=json.dumps({'errors': 1}))
        response = self.client.post(self.list_url,
                                    json.dumps({'upload': upload.pk}))
        eq_(response.status_code, 400)

    def test_not_an_addon(self):
        upload = self.get_upload(
            abspath=self.packaged_app_path('mozball.zip'), user=self.user)
        response = self.client.post(self.list_url,
                                    json.dumps({'upload': upload.pk}))
        eq_(response.status_code, 400)
        ok_(u'manifest.json' in response.json['detail'])


class TestExtensionViewSetGet(UploadTest, RestOAuth):
    fixtures = fixture('user_2519', 'user_999')

    def setUp(self):
        super(TestExtensionViewSetGet, self).setUp()
        self.list_url = reverse('api-v2:extension-list')
        self.user = UserProfile.objects.get(pk=2519)
        self.user2 = UserProfile.objects.get(pk=999)
        self.extension = Extension.objects.create(name=u'Mŷ Extension',
                                                  status=STATUS_PENDING,
                                                  version='0.42')
        self.extension.authors.add(self.user)
        self.extension2 = Extension.objects.create(name=u'NOT Mŷ Extension',
                                                   status=STATUS_PENDING)
        self.extension2.authors.add(self.user2)
        self.url = reverse('api-v2:extension-detail',
                           kwargs={'pk': self.extension.pk})
        self.url2 = reverse('api-v2:extension-detail',
                            kwargs={'pk': self.extension2.pk})

    def test_list_anonymous(self):
        response = self.anon.get(self.list_url)
        eq_(response.status_code, 403)

    def test_list_logged_in(self):
        response = self.client.get(self.list_url)
        eq_(response.status_code, 200)
        meta = response.json['meta']
        eq_(meta['total_count'], 1)
        eq_(len(response.json['objects']), 1)
        data = response.json['objects'][0]
        eq_(data['id'], self.extension.id)
        eq_(data['slug'], self.extension.slug)
        eq_(data['status'], 'pending')
        eq_(data['name'], {"en-US": self.extension.name})
        eq_(data['version'], self.extension.version)

    def test_detail_anonymous(self):
        response = self.anon.get(self.url)
        eq_(response.status_code, 403)

        self.extension.update(status=STATUS_PUBLIC)
        response = self.anon.get(self.url)
        eq_(response.status_code, 200)
        data = response.json
        eq_(data['id'], self.extension.id)
        eq_(data['name'], {'en-US': self.extension.name})
        eq_(data['slug'], self.extension.slug)
        eq_(data['status'], 'public')
        eq_(data['version'], self.extension.version)

    def test_detail_logged_in(self):
        response = self.client.get(self.url2)
        eq_(response.status_code, 403)

        # user is the owner, he can access the extension even if it's not
        # public.
        response = self.client.get(self.url)
        eq_(response.status_code, 200)
        data = response.json
        eq_(data['id'], self.extension.id)
        eq_(data['name'], {'en-US': self.extension.name})
        eq_(data['slug'], self.extension.slug)
        eq_(data['status'], 'pending')
        eq_(data['version'], self.extension.version)


class TestExtensionSearchView(RestOAuth, ESTestCase):
    fixtures = fixture('user_2519')

    def setUp(self):
        self.extension = Extension.objects.create(**{
            'name': u'Mŷ Extension',
            'status': STATUS_PUBLIC,
        })
        self.url = reverse('api-v2:extension-search')
        super(TestExtensionSearchView, self).setUp()
        self.refresh('extension')

    def tearDown(self):
        Extension.get_indexer().unindexer(_all=True)
        super(TestExtensionSearchView, self).tearDown()

    def test_verbs(self):
        self._allowed_verbs(self.url, ['get'])

    def test_has_cors(self):
        self.assertCORS(self.anon.get(self.url), 'get')

    def test_basic(self):
        with self.assertNumQueries(0):
            response = self.anon.get(self.url)
        eq_(response.status_code, 200)
        eq_(len(response.json['objects']), 1)
        data = response.json['objects'][0]
        eq_(data['id'], self.extension.id)
        eq_(data['name'], {'en-US': self.extension.name})
        eq_(data['slug'], self.extension.slug)
        eq_(data['status'], 'public')
        eq_(data['version'], self.extension.version)

    def test_list(self):
        self.extension2 = Extension.objects.create(**{
            'name': u'Mŷ Second Extension',
            'status': STATUS_PUBLIC,
        })
        self.refresh('extension')
        with self.assertNumQueries(0):
            response = self.anon.get(self.url)
        eq_(response.status_code, 200)
        eq_(len(response.json['objects']), 2)

    def test_not_public(self):
        self.extension.update(status=STATUS_PENDING)
        self.refresh('extension')
        with self.assertNumQueries(0):
            response = self.anon.get(self.url)
        eq_(response.status_code, 200)
        eq_(len(response.json['objects']), 0)
