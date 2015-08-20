import base64
import hashlib
import json
import os

from django.core.urlresolvers import reverse

from mock import patch
from nose.tools import eq_, ok_
from PIL import Image, ImageChops

import mkt
from mkt.api.tests.test_oauth import RestOAuth
from mkt.files.models import FileUpload
from mkt.site.fixtures import fixture
from mkt.site.storage_utils import public_storage
from mkt.site.tests import MktPaths
from mkt.site.tests.test_utils_ import get_image_path
from mkt.users.models import UserProfile
from mkt.webapps.models import AddonUser, Webapp


def fake_fetch_manifest(url, upload_pk=None, **kw):
    upload = FileUpload.objects.get(pk=upload_pk)
    upload.update(validation=json.dumps({'fake_validation': True}))


class ValidationHandler(RestOAuth):
    fixtures = fixture('user_2519', 'user_admin')

    def setUp(self):
        super(ValidationHandler, self).setUp()
        self.list_url = reverse('app-validation-list')
        self.get_url = None
        self.user = UserProfile.objects.get(pk=2519)

    def test_has_cors(self):
        self.assertCORS(self.client.get(self.list_url), 'post', 'get')

    @patch('mkt.submit.views.tasks')
    def create(self, tasks_mock, client=None):
        tasks_mock.fetch_manifest.side_effect = fake_fetch_manifest
        manifest_url = u'http://foo.com/'

        if client is None:
            client = self.client

        res = client.post(self.list_url,
                          data=json.dumps({'manifest': manifest_url}))
        data = json.loads(res.content)
        self.get_url = reverse('app-validation-detail',
                               kwargs={'pk': data['id']})
        eq_(tasks_mock.fetch_manifest.call_args[0][0], manifest_url)
        eq_(tasks_mock.fetch_manifest.call_args[0][1], data['id'])
        return res, data

    def get(self):
        return FileUpload.objects.all()[0]

    def get_error(self, response):
        return json.loads(response.content)


class TestAddValidationHandler(ValidationHandler):

    def test_verbs(self):
        self._allowed_verbs(self.list_url, ['post'])

    def test_good(self):
        res, data = self.create()
        eq_(res.status_code, 201)
        eq_(data['processed'], True)
        obj = FileUpload.objects.get(uuid=data['id'])
        eq_(obj.user, self.user)

    def test_missing(self):
        res = self.client.post(self.list_url, data=json.dumps({}))
        eq_(res.status_code, 400)
        eq_(self.get_error(res)['manifest'], ['This field is required.'])

    def test_bad(self):
        res = self.client.post(self.list_url,
                               data=json.dumps({'manifest': 'blurgh'}))
        eq_(res.status_code, 400)
        eq_(self.get_error(res)['manifest'], ['Enter a valid URL.'])

    def test_anon(self):
        res, data = self.create(client=self.anon)
        eq_(res.status_code, 201)
        eq_(data['processed'], True)
        obj = FileUpload.objects.get(uuid=data['id'])
        eq_(obj.user, None)


class TestPackagedValidation(MktPaths, ValidationHandler):

    def setUp(self):
        super(TestPackagedValidation, self).setUp()
        name = 'mozball.zip'
        path = self.packaged_app_path(name)
        contents = open(path).read()
        self.hash = hashlib.sha256(contents).hexdigest()
        self.file = base64.b64encode(contents)
        self.data = {'data': self.file, 'name': name,
                     'type': 'application/zip'}

    @patch('mkt.submit.views.tasks')
    def create(self, tasks_mock, client=None):
        if client is None:
            client = self.client

        res = client.post(self.list_url,
                          data=json.dumps({'upload': self.data}))
        data = json.loads(res.content)
        self.get_url = reverse('app-validation-detail',
                               kwargs={'pk': data['id']})
        eq_(tasks_mock.validator.delay.call_args[0][0], data['id'])
        return res

    def test_good(self):
        res = self.create()
        eq_(res.status_code, 202)
        content = json.loads(res.content)
        eq_(content['processed'], False)
        obj = FileUpload.objects.get(uuid=content['id'])
        eq_(obj.user, self.user)
        eq_(obj.hash, 'sha256:%s' % self.hash)

    @patch('mkt.developers.forms.MAX_PACKAGED_APP_SIZE', 2)
    def test_too_big(self):
        res = self.client.post(self.list_url,
                               data=json.dumps({'upload': self.data}))
        eq_(res.status_code, 400)
        eq_(json.loads(res.content)['upload'][0],
            'Packaged app too large for submission. '
            'Packages must be smaller than 2 bytes.')

    def form_errors(self, data, errors):
        res = self.client.post(self.list_url,
                               data=json.dumps({'upload': data}))
        eq_(res.status_code, 400)
        eq_(self.get_error(res)['upload'], errors)

    def test_missing(self):
        self.form_errors({'data': self.file, 'name': 'mozball.zip'},
                         [u'Type and data are required.'])

    def test_missing_name(self):
        self.form_errors({'data': self.file, 'type': 'application/zip'},
                         [u'Name not specified.'])

    def test_wrong(self):
        self.form_errors({'data': self.file, 'name': 'mozball.zip',
                          'type': 'application/foo'},
                         [u'Type must be application/zip.'])

    def test_invalid(self):
        self.form_errors({'data': 'x', 'name': 'mozball.zip',
                          'type': 'application/foo'},
                         [u'File must be base64 encoded.'])


class TestGetValidationHandler(ValidationHandler):

    def create(self):
        res = FileUpload.objects.create(user=self.user, path='http://foo.com')
        self.get_url = reverse('app-validation-detail', kwargs={'pk': res.pk})
        return res

    def test_verbs(self):
        self.create()
        self._allowed_verbs(self.get_url, ['get'])

    def test_check(self):
        self.create()
        res = self.client.get(self.get_url)
        eq_(res.status_code, 200)

    def test_anon(self):
        self.create()
        res = self.anon.get(self.get_url)
        eq_(res.status_code, 200)

    def test_not_found(self):
        url = reverse('app-validation-detail', kwargs={'pk': 12121212121212})
        res = self.client.get(url)
        eq_(res.status_code, 404)

    def test_not_run(self):
        self.create()
        res = self.client.get(self.get_url)
        eq_(res.status_code, 200)
        eq_(json.loads(res.content)['processed'], False)

    def test_pass(self):
        obj = self.create()
        obj.update(valid=True)
        res = self.client.get(self.get_url)
        eq_(res.status_code, 200)
        data = json.loads(res.content)
        eq_(data['processed'], True)
        eq_(data['valid'], True)

    def test_failure(self):
        obj = self.create()
        error = '{"errors": 1, "messages": [{"tier": 1, "message": "nope"}]}'
        obj.update(valid=False, validation=error)
        res = self.client.get(self.get_url)
        eq_(res.status_code, 200)
        data = json.loads(res.content)
        eq_(data['processed'], True)
        eq_(data['valid'], False)


class TestAppStatusHandler(RestOAuth, MktPaths):
    fixtures = fixture('user_2519', 'webapp_337141')

    def setUp(self):
        super(TestAppStatusHandler, self).setUp()
        self.app = Webapp.objects.get(pk=337141)
        AddonUser.objects.create(addon=self.app, user=self.user)
        self.get_url = reverse('app-status-detail', kwargs={'pk': self.app.pk})

    def get(self, expected_status=200):
        res = self.client.get(self.get_url)
        eq_(res.status_code, expected_status)
        data = json.loads(res.content)
        return res, data

    def test_verbs(self):
        self._allowed_verbs(self.get_url, ['get', 'patch'])

    def test_has_no_cors(self):
        res = self.client.get(self.get_url)
        assert 'access-control-allow-origin' not in res

    def test_status(self):
        res, data = self.get()
        eq_(self.app.status, mkt.STATUS_PUBLIC)
        eq_(data['status'], 'public')
        eq_(data['disabled_by_user'], False)

        self.app.update(status=mkt.STATUS_UNLISTED)
        res, data = self.get()
        eq_(data['status'], 'unlisted')
        eq_(data['disabled_by_user'], False)

        self.app.update(status=mkt.STATUS_NULL)
        res, data = self.get()
        eq_(data['status'], 'incomplete')
        eq_(data['disabled_by_user'], False)

        self.app.update(status=mkt.STATUS_PENDING)
        res, data = self.get()
        eq_(data['status'], 'pending')
        eq_(data['disabled_by_user'], False)

        self.app.update(disabled_by_user=True)
        res, data = self.get()
        eq_(data['status'], 'pending')
        eq_(data['disabled_by_user'], True)

    def test_status_not_mine(self):
        AddonUser.objects.get(user=self.user).delete()
        res = self.client.get(self.get_url)
        eq_(res.status_code, 403)

    def test_disable(self):
        eq_(self.app.disabled_by_user, False)
        res = self.client.patch(self.get_url,
                                data=json.dumps({'disabled_by_user': True}))
        eq_(res.status_code, 200)
        self.app.reload()
        data = json.loads(res.content)
        eq_(data['status'], 'public')
        eq_(self.app.disabled_by_user, True)
        eq_(self.app.status, mkt.STATUS_PUBLIC)  # Unchanged, doesn't matter.

    def test_disable_not_mine(self):
        AddonUser.objects.get(user=self.user).delete()
        res = self.client.patch(self.get_url,
                                data=json.dumps({'disabled_by_user': True}))
        eq_(res.status_code, 403)

    def test_change_status_to_pending_fails(self):
        res = self.client.patch(self.get_url,
                                data=json.dumps({'status': 'pending'}))
        eq_(res.status_code, 400)
        data = json.loads(res.content)
        ok_('status' in data)

    def test_change_status_to_public_fails(self):
        self.app.update(status=mkt.STATUS_PENDING)
        res = self.client.patch(self.get_url,
                                data=json.dumps({'status': 'public'}))
        eq_(res.status_code, 400)
        data = json.loads(res.content)
        ok_('status' in data)
        eq_(self.app.reload().status, mkt.STATUS_PENDING)

    @patch('mkt.webapps.models.Webapp.is_fully_complete')
    def test_incomplete_app(self, is_fully_complete):
        is_fully_complete.return_value = False
        self.app.update(status=mkt.STATUS_NULL)
        res = self.client.patch(self.get_url,
                                data=json.dumps({'status': 'pending'}))
        eq_(res.status_code, 400)
        data = json.loads(res.content)
        self.assertSetEqual(data['status'], self.app.completion_error_msgs())

    @patch('mkt.webapps.models.Webapp.is_fully_complete')
    def test_status_changes(self, is_fully_complete):
        is_fully_complete.return_value = True

        # Statuses we want to check in (from, [to, ...]) tuples.
        status_changes = (
            (mkt.STATUS_NULL, [mkt.STATUS_PENDING]),
            (mkt.STATUS_APPROVED, [mkt.STATUS_UNLISTED, mkt.STATUS_PUBLIC]),
            (mkt.STATUS_UNLISTED, [mkt.STATUS_APPROVED, mkt.STATUS_PUBLIC]),
            (mkt.STATUS_PUBLIC, [mkt.STATUS_APPROVED, mkt.STATUS_UNLISTED]),
        )

        for orig, new in status_changes:
            for to in new:
                self.app.update(status=orig)
                to_api_status = mkt.STATUS_CHOICES_API[to]
                res = self.client.patch(
                    self.get_url, data=json.dumps({'status': to_api_status}))
                eq_(res.status_code, 200)
                data = json.loads(res.content)
                eq_(data['status'], to_api_status)
                eq_(self.app.reload().status, to)

    @patch('mkt.webapps.models.Webapp.is_fully_complete')
    def test_senior_reviewer_incomplete_to_pending(self, is_fully_complete):
        # The app is incomplete, but the user has Admin:%s so he can override
        # that.
        is_fully_complete.return_value = False
        self.grant_permission(self.user, 'Admin:%s')
        self.app.update(status=mkt.STATUS_NULL)
        res = self.client.patch(self.get_url,
                                data=json.dumps({'status': 'pending'}))
        eq_(res.status_code, 200)
        data = json.loads(res.content)
        eq_(data['status'], 'pending')
        eq_(self.app.reload().status, mkt.STATUS_PENDING)

    @patch('mkt.webapps.models.Webapp.is_fully_complete')
    def test_senior_reviewer_incomplete_to_public(self, is_fully_complete):
        # The app is incomplete, but the user has Admin:%s so he can override
        # that.
        is_fully_complete.return_value = False
        self.grant_permission(self.user, 'Admin:%s')
        self.app.update(status=mkt.STATUS_NULL)
        res = self.client.patch(self.get_url,
                                data=json.dumps({'status': 'public'}))
        eq_(res.status_code, 200)
        data = json.loads(res.content)
        eq_(data['status'], 'public')
        eq_(self.app.reload().status, mkt.STATUS_PUBLIC)


class TestPreviewHandler(RestOAuth, MktPaths):
    fixtures = fixture('user_2519', 'webapp_337141')

    def setUp(self):
        super(TestPreviewHandler, self).setUp()
        self.app = Webapp.objects.get(pk=337141)
        self.user = UserProfile.objects.get(pk=2519)
        AddonUser.objects.create(user=self.user, addon=self.app)
        self.file = base64.b64encode(
            open(get_image_path('preview.jpg'), 'r').read())
        self.list_url = reverse('app-preview',
                                kwargs={'pk': self.app.pk})
        self.good = {'file': {'data': self.file, 'type': 'image/jpg'},
                     'position': 1}

    def get_error(self, response):
        return json.loads(response.content)

    def test_has_cors(self):
        self.assertCORS(self.client.post(self.list_url),
                        'post', 'delete', 'get')

    def test_post_preview(self):
        res = self.client.post(self.list_url, data=json.dumps(self.good))
        eq_(res.status_code, 201)
        previews = self.app.previews
        eq_(previews.count(), 1)
        eq_(previews.all()[0].position, 1)

    def test_wrong_url(self):
        self.list_url = reverse('app-preview',
                                kwargs={'pk': 'booyah'})
        res = self.client.post(self.list_url, data=json.dumps(self.good))
        eq_(res.status_code, 404)
        data = json.loads(res.content)
        eq_(data['detail'], 'Not found')

    def test_not_mine(self):
        self.app.authors.clear()
        res = self.client.post(self.list_url, data=json.dumps(self.good))
        eq_(res.status_code, 403)

    def test_position_missing(self):
        data = {'file': {'data': self.file, 'type': 'image/jpg'}}
        res = self.client.post(self.list_url, data=json.dumps(data))
        eq_(res.status_code, 400)
        eq_(self.get_error(res)['position'], ['This field is required.'])

    def test_preview_missing(self):
        res = self.client.post(self.list_url, data=json.dumps({}))
        eq_(res.status_code, 400)
        eq_(self.get_error(res)['position'], ['This field is required.'])

    def create(self):
        self.client.post(self.list_url, data=json.dumps(self.good))
        self.preview = self.app.previews.all()[0]
        self.get_url = reverse('app-preview-detail',
                               kwargs={'pk': self.preview.pk})

    def test_delete(self):
        self.create()
        res = self.client.delete(self.get_url)
        eq_(res.status_code, 204)
        eq_(self.app.previews.count(), 0)

    def test_delete_not_mine(self):
        self.create()
        self.app.authors.clear()
        res = self.client.delete(self.get_url)
        eq_(res.status_code, 403)

    def test_delete_not_there(self):
        self.get_url = reverse('app-preview-detail',
                               kwargs={'pk': 123123123})
        res = self.client.delete(self.get_url)
        eq_(res.status_code, 404)

    def test_get(self):
        self.create()
        res = self.client.get(self.get_url)
        eq_(res.status_code, 200)

    def test_get_not_mine(self):
        self.create()
        self.app.authors.clear()
        res = self.client.get(self.get_url)
        eq_(res.status_code, 403)

    def test_get_not_there(self):
        self.get_url = reverse('app-preview-detail',
                               kwargs={'pk': 123123123})
        res = self.client.get(self.get_url)
        eq_(res.status_code, 404)


class TestIconUpdate(RestOAuth, MktPaths):
    fixtures = fixture('user_2519', 'webapp_337141')

    def setUp(self):
        super(TestIconUpdate, self).setUp()
        self.app = Webapp.objects.get(pk=337141)
        self.user = UserProfile.objects.get(pk=2519)
        AddonUser.objects.create(user=self.user, addon=self.app)
        self.file = base64.b64encode(open(self.mozball_image(), 'r').read())
        self.url = reverse('app-icon', kwargs={'pk': self.app.pk})
        self.data = {'file': {'data': self.file, 'type': 'image/png'}}

    def images_are_equal(self, image_file_1, image_file_2):
        im1 = Image.open(image_file_1)
        im2 = Image.open(image_file_2)
        return ImageChops.difference(im1, im2).getbbox() is None

    def test_has_cors(self):
        self.assertCORS(self.client.post(self.url), 'put')

    def test_put_icon_success(self):
        res = self.client.put(self.url, data=json.dumps(self.data))
        eq_(res.status_code, 200)

    def test_correct_new_icon(self):
        self.client.put(self.url, data=json.dumps(self.data))
        icon_dir = self.app.get_icon_dir()
        icon_path = os.path.join(icon_dir, '%s-128.png' % str(self.app.id))
        eq_(self.images_are_equal(self.mozball_image(),
                                  public_storage.open(icon_path)), True)

    def test_invalid_owner_permissions(self):
        self.app.authors.clear()
        res = self.client.put(self.url, data=json.dumps(self.data))
        eq_(res.status_code, 403)

    def test_invalid_icon_type(self):
        data = {'file': {'data': self.file, 'type': 'image/gif'}}
        res = self.client.put(self.url, data=json.dumps(data))
        eq_(res.status_code, 400)
        eq_(json.loads(res.content)['file'][0],
            u'Icons must be either PNG or JPG.')
