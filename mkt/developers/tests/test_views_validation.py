# -*- coding: utf-8 -*-
import codecs
import json
import os
import tempfile

from django import forms
from django.core.urlresolvers import reverse
from django.test.client import RequestFactory

from mock import patch
from nose.tools import eq_
from pyquery import PyQuery as pq

from mkt.developers.views import standalone_hosted_upload, trap_duplicate
from mkt.files.models import FileUpload
from mkt.files.tests.test_models import UploadTest as BaseUploadTest
from mkt.files.utils import WebAppParser
from mkt.site.fixtures import fixture
from mkt.site.storage_utils import (copy_stored_file, local_storage,
                                    private_storage, storage_is_remote)
from mkt.site.tests import MktPaths, TestCase
from mkt.site.tests.test_utils_ import get_image_path
from mkt.submit.tests.test_views import BaseWebAppTest
from mkt.users.models import UserProfile


class TestWebApps(TestCase, MktPaths):

    def setUp(self):
        self.webapp_path = tempfile.mktemp(suffix='.webapp')
        copy_stored_file(
            self.manifest_path('mozball.webapp'), self.webapp_path,
            src_storage=local_storage, dst_storage=private_storage)
        self.tmp_files = []
        self.manifest = dict(name=u'Ivan Krsti\u0107', version=u'1.0',
                             description=u'summary',
                             developer=dict(name=u'Dev Namé'))

    def tearDown(self):
        for tmp in self.tmp_files:
            private_storage.delete(tmp)

    def webapp(self, data=None, contents='', suffix='.webapp'):
        tmp = tempfile.mktemp(suffix=suffix)
        self.tmp_files.append(tmp)
        with private_storage.open(tmp, 'wb') as f:
            f.write(json.dumps(data) if data else contents)
        return private_storage.open(tmp)

    def test_parse(self):
        wp = WebAppParser().parse(private_storage.open(self.webapp_path))
        eq_(wp['guid'], None)
        eq_(wp['description']['en-US'],
            u'Exciting Open Web development action!')
        # UTF-8 byte string decoded to unicode.
        eq_(wp['description']['es'],
            u'\xa1Acci\xf3n abierta emocionante del desarrollo del Web!')
        eq_(wp['description']['it'],
            u'Azione aperta emozionante di sviluppo di fotoricettore!')
        eq_(wp['version'], '1.0')
        eq_(wp['default_locale'], 'en-US')

    def test_parse_packaged(self):
        path = self.packaged_app_path('mozball.zip')
        if storage_is_remote():
            copy_stored_file(path, path, src_storage=local_storage,
                             dst_storage=private_storage)
        wp = WebAppParser().parse(private_storage.open(path))
        eq_(wp['guid'], None)
        eq_(wp['name']['en-US'], u'Packaged MozillaBall ょ')
        eq_(wp['description']['en-US'],
            u'Exciting Open Web development action!')
        eq_(wp['description']['es'],
            u'¡Acción abierta emocionante del desarrollo del Web!')
        eq_(wp['description']['it'],
            u'Azione aperta emozionante di sviluppo di fotoricettore!')
        eq_(wp['version'], '1.0')
        eq_(wp['default_locale'], 'en-US')

    def test_parse_packaged_BOM(self):
        path = self.packaged_app_path('mozBOM.zip')
        if storage_is_remote():
            copy_stored_file(path, path, src_storage=local_storage,
                             dst_storage=private_storage)
        wp = WebAppParser().parse(private_storage.open(path))
        eq_(wp['guid'], None)
        eq_(wp['name']['en-US'], u'Packaged MozBOM ょ')
        eq_(wp['description']['en-US'], u'Exciting BOM action!')
        eq_(wp['description']['es'], u'¡Acción BOM!')
        eq_(wp['description']['it'], u'Azione BOM!')
        eq_(wp['version'], '1.0')
        eq_(wp['default_locale'], 'en-US')

    def test_no_manifest_at_root(self):
        path = self.packaged_app_path('no-manifest-at-root.zip')
        if storage_is_remote():
            copy_stored_file(path, path, src_storage=local_storage,
                             dst_storage=private_storage)
        with self.assertRaises(forms.ValidationError) as exc:
            WebAppParser().parse(private_storage.open(path))
        m = exc.exception.messages[0]
        assert m.startswith('The file "manifest.webapp" was not found'), (
            'Unexpected: %s' % m)

    def test_no_locales(self):
        wp = WebAppParser().parse(self.webapp(
            dict(name='foo', version='1.0', description='description',
                 developer=dict(name='bar'))))
        eq_(wp['description']['en-US'], u'description')

    def test_no_description(self):
        wp = WebAppParser().parse(self.webapp(
            dict(name='foo', version='1.0', developer=dict(name='bar'))))
        eq_(wp['description'], {})

    def test_syntax_error(self):
        with self.assertRaises(forms.ValidationError) as exc:
            WebAppParser().parse(self.webapp(contents='}]'))
        m = exc.exception.messages[0]
        assert m.startswith('The webapp manifest is not valid JSON.'), (
            'Unexpected: %s' % m)

    def test_utf8_bom(self):
        wm = codecs.BOM_UTF8 + json.dumps(self.manifest, encoding='utf8')
        wp = WebAppParser().parse(self.webapp(contents=wm))
        eq_(wp['version'], '1.0')

    def test_non_ascii(self):
        wm = json.dumps(dict(name=u'まつもとゆきひろ', version='1.0',
                             developer=dict(name=u'まつもとゆきひろ')),
                        encoding='shift-jis')
        wp = WebAppParser().parse(self.webapp(contents=wm))
        eq_(wp['name'], {'en-US': u'まつもとゆきひろ'})


class TestTrapDuplicate(BaseWebAppTest):

    def setUp(self):
        super(TestTrapDuplicate, self).setUp()
        self.create_switch('webapps-unique-by-domain')
        self.req = RequestFactory().get('/')
        self.req.user = UserProfile.objects.get(pk=999)

    @patch('mkt.developers.views.trap_duplicate')
    def test_trap_duplicate_skipped_on_standalone(self, trap_duplicate_mock):
        self.post()
        standalone_hosted_upload(self.req)
        assert not trap_duplicate_mock.called

    def test_trap_duplicate(self):
        self.post_webapp()
        standalone_hosted_upload(self.req)
        assert trap_duplicate(self.req, 'http://allizom.org/mozball.webapp')


class TestStandaloneValidation(BaseUploadTest):
    fixtures = fixture('user_999')

    def setUp(self):
        super(TestStandaloneValidation, self).setUp()
        self.login('regular@mozilla.com')

        # Upload URLs
        self.hosted_upload = reverse(
            'mkt.developers.standalone_hosted_upload')
        self.packaged_upload = reverse(
            'mkt.developers.standalone_packaged_upload')

    def hosted_detail(self, uuid):
        return reverse('mkt.developers.standalone_upload_detail',
                       args=['hosted', uuid])

    def packaged_detail(self, uuid):
        return reverse('mkt.developers.standalone_upload_detail',
                       args=['packaged', uuid])

    def upload_detail(self, uuid):
        return reverse('mkt.developers.upload_detail', args=[uuid])

    def test_context(self):
        res = self.client.get(reverse('mkt.developers.validate_app'))
        eq_(res.status_code, 200)
        doc = pq(res.content)
        eq_(doc('#upload-webapp-url').attr('data-upload-url'),
            self.hosted_upload)
        eq_(doc('#upload-app').attr('data-upload-url'), self.packaged_upload)

    def detail_view(self, url_factory, upload):
        res = self.client.get(url_factory(upload.uuid))
        res_json = json.loads(res.content)
        eq_(res_json['url'], url_factory(upload.uuid))
        eq_(res_json['full_report_url'], self.upload_detail(upload.uuid))

        res = self.client.get(self.upload_detail(upload.uuid))
        eq_(res.status_code, 200)
        doc = pq(res.content)
        assert doc('header h1').text().startswith('Validation Results for ')
        suite = doc('#addon-validator-suite')

        # All apps have a `validateurl` value that corresponds to a hosted app.
        eq_(suite.attr('data-validateurl'), self.hosted_detail(upload.uuid))

    @patch('mkt.developers.tasks._fetch_manifest')
    def test_hosted_detail(self, fetch_manifest):
        def update_upload(url, upload):
            with open(os.path.join(os.path.dirname(__file__),
                                   'webapps', 'mozball.webapp'), 'r') as data:
                return data.read()

        fetch_manifest.side_effect = update_upload

        res = self.client.post(
            self.hosted_upload, {'manifest': 'http://foo.bar/'}, follow=True)
        eq_(res.status_code, 200)

        uuid = json.loads(res.content)['upload']
        upload = FileUpload.objects.get(uuid=uuid)
        eq_(upload.user.pk, 999)
        self.detail_view(self.hosted_detail, upload)

    def test_packaged_detail(self):
        data = open(get_image_path('animated.png'), 'rb')
        self.client.post(self.packaged_upload, {'upload': data})
        upload = FileUpload.objects.get(name='animated.png')
        self.detail_view(self.packaged_detail, upload)
