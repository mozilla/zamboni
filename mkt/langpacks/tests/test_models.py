# -*- coding: utf-8 -*-
import json
import os

from django.conf import settings
from django.forms import ValidationError

from mock import patch
from nose.tools import eq_, ok_

from lib.crypto.packaged import SigningError
from mkt.files.tests.test_models import UploadCreationMixin, UploadTest
from mkt.langpacks.models import LangPack
from mkt.site.tests import TestCase
from mkt.site.storage_utils import private_storage, public_storage


class TestLangPackBasic(TestCase):
    def reset_uuid(self):
        langpack = LangPack(uuid='12345678123456781234567812345678')
        eq_(langpack.pk, '12345678123456781234567812345678')
        langpack.reset_uuid()
        ok_(langpack.pk != '12345678123456781234567812345678')

    def test_download_url(self):
        langpack = LangPack(pk='12345678123456781234567812345678')
        ok_(langpack.download_url.endswith(
            '/12345678123456781234567812345678/langpack.zip'))

    def test_manifest_url(self):
        langpack = LangPack(pk='12345678123456781234567812345678')
        eq_(langpack.manifest_url, '')  # Inactive langpack.
        langpack.active = True
        ok_(langpack.manifest_url.endswith(
            '/12345678-1234-5678-1234-567812345678/manifest.webapp'))

    @patch('mkt.webapps.utils.public_storage')
    def test_get_minifest_contents(self, storage_mock):
        fake_manifest = {
            'name': u'Fake LangPäck',
            'developer': {
                'name': 'Mozilla'
            }
        }
        langpack = LangPack.objects.create(
            pk='12345678123456781234567812345678',
            fxos_version='2.2',
            version='0.3',
            manifest=json.dumps(fake_manifest))
        storage_mock.size.return_value = 666
        minifest_contents = json.loads(langpack.get_minifest_contents()[0])

        eq_(minifest_contents,
            {'version': '0.3',
             'size': 666,
             'name': u'Fake LangPäck',
             'package_path': langpack.download_url,
             'developer': {'name': 'Mozilla'}})
        return langpack, minifest_contents

    def test_get_minifest_contents_caching(self):
        langpack, minifest_contents = self.test_get_minifest_contents()
        langpack.update(manifest='{}')
        # Because of caching, get_minifest_contents should not have changed.
        new_minifest_contents = json.loads(langpack.get_minifest_contents()[0])
        eq_(minifest_contents, new_minifest_contents)

    def test_language_choices_and_display(self):
        field = LangPack._meta.get_field('language')
        eq_(len(field.choices), len(settings.LANGUAGES))
        eq_(LangPack(language='fr').get_language_display(), u'Français')
        eq_(LangPack(language='en-US').get_language_display(), u'English (US)')

    def test_sort(self):
        langpack_it = LangPack.objects.create(language='it')
        langpack_de = LangPack.objects.create(language='de')
        langpack_fr = LangPack.objects.create(language='fr')
        eq_(list(LangPack.objects.all()),
            [langpack_de, langpack_fr, langpack_it])


class TestLangPackUpload(UploadCreationMixin, UploadTest):
    # Expected manifest, to test zip file parsing.
    expected_manifest = {
        'languages-target': {
            'app://*.gaiamobile.org/manifest.webapp': '2.2'
        },
        'description': 'Support for additional language: German',
        'default_locale': 'de',
        'icons': {
            '128': '/icon.png'
        },
        'version': '1.0.3',
        'role': 'langpack',
        'languages-provided': {
            'de': {
                'revision': 201411051234,
                'apps': {
                    'app://calendar.gaiamobile.org/manifest.webapp':
                    '/de/calendar',
                    'app://email.gaiamobile.org/manifest.webapp':
                    '/de/email'
                },
                'name': 'Deutsch'
            }
        },
        'developer': {
            'name': 'Mozilla'
        },
        'type': 'privileged', 'locales': {
            'de': {
                'name': u'Sprachpaket für Gaia: Deutsch'
            },
            'pl': {
                'name': u'Paczka językowa dla Gai: niemiecki'
            }
        },
        'name': 'Gaia Langpack for German'
    }

    def create_langpack(self):
        langpack = LangPack.objects.create(
            language='fr', version='0.9', fxos_version='2.1', active=False,
            file_version=1, manifest='{}')
        return langpack

    def test_upload_new(self):
        eq_(LangPack.objects.count(), 0)
        upload = self.upload('langpack')
        langpack = LangPack.from_upload(upload)
        ok_(langpack.uuid)
        eq_(langpack.file_version, 1)
        eq_(langpack.version, '1.0.3')
        eq_(langpack.language, 'de')
        eq_(langpack.fxos_version, '2.2')
        eq_(langpack.filename, '%s-%s.zip' % (langpack.uuid, langpack.version))
        ok_(langpack.filename in langpack.file_path)
        ok_(langpack.file_path.startswith(langpack.path_prefix))
        ok_(public_storage.exists(langpack.file_path))
        eq_(langpack.get_manifest_json(), self.expected_manifest)
        ok_(LangPack.objects.get(pk=langpack.uuid))
        eq_(LangPack.objects.count(), 1)
        return langpack

    def test_upload_existing(self):
        langpack = self.create_langpack()
        original_uuid = langpack.uuid
        original_file_path = langpack.file_path
        original_file_version = langpack.file_version
        original_manifest = langpack.manifest
        with patch('mkt.webapps.utils.public_storage') as storage_mock:
            # mock storage size before building minifest since we haven't
            # created a real file for this langpack yet.
            storage_mock.size.return_value = 666
            original_minifest = langpack.get_minifest_contents()
        upload = self.upload('langpack')
        langpack = LangPack.from_upload(upload, instance=langpack)
        eq_(langpack.uuid, original_uuid)
        eq_(langpack.version, '1.0.3')
        eq_(langpack.language, 'de')
        eq_(langpack.fxos_version, '2.2')
        eq_(langpack.filename, '%s-%s.zip' % (langpack.uuid, langpack.version))
        eq_(langpack.get_manifest_json(), self.expected_manifest)
        ok_(langpack.file_path.startswith(langpack.path_prefix))
        ok_(langpack.filename in langpack.file_path)
        ok_(langpack.file_path != original_file_path)
        ok_(langpack.file_version > original_file_version)
        ok_(public_storage.exists(langpack.file_path))
        ok_(LangPack.objects.get(pk=langpack.uuid))
        eq_(LangPack.objects.count(), 1)
        ok_(langpack.manifest != original_manifest)
        # We're supposed to have busted the old minifest cache.
        ok_(langpack.get_minifest_contents() != original_minifest)

    @patch('mkt.files.utils.WebAppParser.get_json_data')
    def test_upload_language_validation(self, get_json_data_mock):
        upload = self.upload('langpack')
        get_json_data_mock.return_value = {
            'name': 'Portuguese Langpack',
            'developer': {
                'name': 'Mozilla'
            },
            'role': 'langpack',
            'languages-provided': {
                'pt-BR': {}
            },
            'languages-target': {
                'app://*.gaiamobile.org/manifest.webapp': '2.2'
            },
            'version': '0.1'
        }
        langpack = LangPack.from_upload(upload)
        ok_(langpack.pk)
        eq_(langpack.language, 'pt-BR')
        get_json_data_mock.return_value['languages-provided'] = {
            'invalid-lang': {}
        }
        expected = [u"Value 'invalid-lang' is not a valid choice."]
        with self.assertRaises(ValidationError) as e:
            LangPack.from_upload(upload)
        eq_(e.exception.messages, expected)

    def test_upload_existing_same_version(self):
        langpack = self.create_langpack()
        upload = self.upload('langpack')
        # Works once.
        ok_(LangPack.from_upload(upload, instance=langpack))
        # Doesn't work twice, since we are re-uploading the same version.
        expected = [u'Your language pack version must be different to the '
                    u'one you are replacing.']
        with self.assertRaises(ValidationError) as e:
            LangPack.from_upload(upload, instance=langpack)
        eq_(e.exception.messages, expected)

    @patch('mkt.langpacks.models.get_cached_minifest')
    @patch('mkt.langpacks.models.sign_app')
    def test_upload_sign(self, sign_app_mock, cached_minifest_mock):
        eq_(LangPack.objects.count(), 0)
        upload = self.upload('langpack')
        langpack = LangPack.from_upload(upload)
        ok_(langpack.pk)
        ok_(langpack.file_version)
        ok_(langpack.file_path)
        eq_(LangPack.objects.count(), 1)
        expected_args = (
            langpack.file_path,
            json.dumps({'id': langpack.pk, 'version': langpack.file_version})
        )
        eq_(os.path.join('/', sign_app_mock.call_args[0][0].name), upload.path)
        eq_(sign_app_mock.call_args[0][1:], expected_args)

    @patch('mkt.langpacks.models.get_cached_minifest')
    @patch('mkt.langpacks.models.sign_app')
    def test_upload_sign_existing(self, sign_app_mock, cached_minifest_mock):
        langpack = self.create_langpack()
        eq_(LangPack.objects.count(), 1)
        upload = self.upload('langpack')
        langpack = LangPack.from_upload(upload, instance=langpack)
        ok_(langpack.pk)
        ok_(langpack.file_version)
        ok_(langpack.file_path)
        eq_(LangPack.objects.count(), 1)
        expected_args = (
            langpack.file_path,
            json.dumps({'id': langpack.pk, 'version': langpack.file_version})
        )
        eq_(os.path.join('/', sign_app_mock.call_args[0][0].name), upload.path)
        eq_(sign_app_mock.call_args[0][1:], expected_args)

    @patch('mkt.langpacks.models.sign_app')
    def test_upload_sign_error(self, sign_app_mock):
        sign_app_mock.side_effect = SigningError
        eq_(LangPack.objects.count(), 0)
        upload = self.upload('langpack')
        with self.assertRaises(SigningError):
            LangPack.from_upload(upload)
        # Test that we didn't delete the upload file
        ok_(private_storage.exists(upload.path))

    @patch('mkt.langpacks.models.sign_app')
    def test_upload_sign_error_existing(self, sign_app_mock):
        sign_app_mock.side_effect = SigningError
        langpack = self.create_langpack()
        eq_(LangPack.objects.count(), 1)
        original_uuid = langpack.uuid
        original_file_path = langpack.file_path
        original_file_version = langpack.file_version
        original_version = langpack.version
        # create_langpack() doesn't create a fake file, let's add one.
        with public_storage.open(langpack.file_path, 'w') as f:
            f.write('.')
        upload = self.upload('langpack')
        with self.assertRaises(SigningError):
            LangPack.from_upload(upload, instance=langpack)
        # Test that we didn't delete the upload file
        ok_(private_storage.exists(upload.path))
        # Test that we didn't delete the existing filename or alter the
        # existing langpack in the database.
        eq_(LangPack.objects.count(), 1)
        langpack.reload()
        eq_(original_uuid, langpack.uuid)
        eq_(langpack.file_path, original_file_path)
        eq_(original_file_version, langpack.file_version)
        eq_(original_version, langpack.version)
        ok_(public_storage.exists(langpack.file_path))

        # Cleanup
        public_storage.delete(langpack.file_path)


class TestLangPackDeletion(TestCase):
    def test_delete_with_file(self):
        """Test that when a LangPack instance is deleted, the corresponding
        file on the filesystem is also deleted."""
        langpack = LangPack.objects.create(version='0.1')
        file_path = langpack.file_path
        with public_storage.open(file_path, 'w') as f:
            f.write('sample data\n')
        assert public_storage.exists(file_path)
        try:
            langpack.delete()
            assert not public_storage.exists(file_path)
        finally:
            if public_storage.exists(file_path):
                public_storage.delete(file_path)

    def test_delete_no_file(self):
        """Test that the LangPack instance can be deleted without the file
        being present."""
        langpack = LangPack.objects.create(version='0.1')
        filename = langpack.file_path
        x = public_storage.exists(filename)
        assert not x, 'File exists at: %s' % filename
        langpack.delete()

    def test_delete_signal(self):
        """Test that the LangPack instance can be deleted with the filename
        field being empty."""
        langpack = LangPack.objects.create()
        langpack.delete()
