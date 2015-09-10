from django.forms.fields import BooleanField
from django.test.client import RequestFactory
from django.utils.safestring import SafeText
from django.utils.translation import ugettext_lazy as _

import mock
from nose.tools import eq_, ok_

import mkt
import mkt.site.tests
from mkt.comm.models import CommunicationNote
from mkt.constants.features import APP_FEATURES
from mkt.developers.models import AppLog
from mkt.files.models import FileUpload
from mkt.reviewers.models import RereviewQueue
from mkt.site.fixtures import fixture
from mkt.site.tests import user_factory
from mkt.submit import forms
from mkt.users.models import UserProfile
from mkt.webapps.models import AppFeatures, Webapp


class TestNewWebappForm(mkt.site.tests.TestCase):

    def setUp(self):
        self.request = RequestFactory().get('/')
        self.request.user = user_factory()
        self.file = FileUpload.objects.create(valid=True)
        self.file.user = self.request.user
        self.file.save()

    def test_no_user(self):
        self.file.user = None
        self.file.save()
        form = forms.NewWebappForm({'free_platforms': ['free-firefoxos'],
                                    'upload': self.file.uuid},
                                   request=self.request)
        assert not form.is_valid()
        eq_(form.ERRORS['user'], form.errors['free_platforms'])
        eq_(form.ERRORS['user'], form.errors['paid_platforms'])

    def test_correct_user(self):
        form = forms.NewWebappForm({'free_platforms': ['free-firefoxos'],
                                    'upload': self.file.uuid},
                                   request=self.request)
        assert form.is_valid(), form.errors

    def test_incorrect_user(self):
        self.file.user = user_factory()
        self.file.save()
        form = forms.NewWebappForm({'upload': self.file.uuid},
                                   request=self.request)
        assert not form.is_valid()
        eq_(form.ERRORS['user'], form.errors['free_platforms'])
        eq_(form.ERRORS['user'], form.errors['paid_platforms'])

    def test_not_free_or_paid(self):
        form = forms.NewWebappForm({})
        assert not form.is_valid()
        eq_(form.ERRORS['none'], form.errors['free_platforms'])
        eq_(form.ERRORS['none'], form.errors['paid_platforms'])

    def test_paid(self):
        form = forms.NewWebappForm({'paid_platforms': ['paid-firefoxos'],
                                    'upload': self.file.uuid},
                                   request=self.request)
        assert form.is_valid()
        eq_(form.get_paid(), mkt.ADDON_PREMIUM)

    def test_free(self):
        form = forms.NewWebappForm({'free_platforms': ['free-firefoxos'],
                                    'upload': self.file.uuid})
        assert form.is_valid()
        eq_(form.get_paid(), mkt.ADDON_FREE)

    def test_platform(self):
        mappings = (
            ({'free_platforms': ['free-firefoxos']}, [mkt.DEVICE_GAIA]),
            ({'paid_platforms': ['paid-firefoxos']}, [mkt.DEVICE_GAIA]),
            ({'free_platforms': ['free-firefoxos',
                                 'free-android-mobile']},
             [mkt.DEVICE_GAIA, mkt.DEVICE_MOBILE]),
            ({'free_platforms': ['free-android-mobile',
                                 'free-android-tablet']},
             [mkt.DEVICE_MOBILE, mkt.DEVICE_TABLET]),
        )
        for data, res in mappings:
            data['upload'] = self.file.uuid
            form = forms.NewWebappForm(data)
            assert form.is_valid(), form.errors
            self.assertSetEqual(res, form.get_devices())

    def test_both(self):
        form = forms.NewWebappForm({'paid_platforms': ['paid-firefoxos'],
                                    'free_platforms': ['free-firefoxos']},
                                   request=self.request)
        assert not form.is_valid()
        eq_(form.ERRORS['both'], form.errors['free_platforms'])
        eq_(form.ERRORS['both'], form.errors['paid_platforms'])

    def test_multiple(self):
        form = forms.NewWebappForm({'free_platforms': ['free-firefoxos',
                                                       'free-desktop'],
                                    'upload': self.file.uuid})
        assert form.is_valid()

    def test_not_packaged(self):
        form = forms.NewWebappForm({'free_platforms': ['free-firefoxos'],
                                    'upload': self.file.uuid})
        assert form.is_valid(), form.errors
        assert not form.is_packaged()

    @mock.patch('mkt.submit.forms.parse_addon',
                lambda *args: {'version': None})
    def test_packaged_allowed_everywhere(self):
        for device in ('free-firefoxos',
                       'free-desktop',
                       'free-android-tablet',
                       'free-android-mobile'):
            form = forms.NewWebappForm({'free_platforms': [device],
                                        'upload': self.file.uuid,
                                        'packaged': True},
                                       request=self.request)
            assert form.is_valid(), form.errors
            assert form.is_packaged()


class TestNewWebappVersionForm(mkt.site.tests.TestCase):

    def setUp(self):
        self.request = RequestFactory().get('/')
        self.file = FileUpload.objects.create(valid=True)

    def test_no_upload(self):
        form = forms.NewWebappVersionForm(request=self.request,
                                          is_packaged=True)
        assert not form.is_valid(), form.errors

    @mock.patch('mkt.submit.forms.parse_addon',
                lambda *args: {"origin": "app://hy.fr"})
    @mock.patch('mkt.submit.forms.verify_app_domain')
    def test_verify_app_domain_called(self, _verify):
        self.create_switch('webapps-unique-by-domain')
        form = forms.NewWebappVersionForm({'upload': self.file.uuid},
                                          request=self.request,
                                          is_packaged=True)
        assert form.is_valid(), form.errors
        assert _verify.called

    @mock.patch('mkt.submit.forms.parse_addon',
                lambda *args: {"origin": "app://hy.fr"})
    def test_verify_app_domain_exclude_same(self):
        app = mkt.site.tests.app_factory(app_domain='app://hy.fr')
        form = forms.NewWebappVersionForm(
            {'upload': self.file.uuid}, request=self.request, is_packaged=True,
            addon=app)
        assert form.is_valid(), form.errors

    @mock.patch('mkt.submit.forms.parse_addon',
                lambda *args: {"origin": "app://hy.fr"})
    def test_verify_app_domain_exclude_different(self):
        app = mkt.site.tests.app_factory(app_domain='app://yo.lo')
        mkt.site.tests.app_factory(app_domain='app://hy.fr')
        form = forms.NewWebappVersionForm(
            {'upload': self.file.uuid}, request=self.request, is_packaged=True,
            addon=app)
        assert not form.is_valid(), form.errors
        assert ('An app already exists on this domain; '
                'only one app per domain is allowed.' in form.errors['upload'])


class TestAppDetailsBasicForm(mkt.site.tests.TestCase):
    fixtures = fixture('user_999', 'webapp_337141')

    def setUp(self):
        self.request = mock.Mock()
        self.request.user = UserProfile.objects.get(id=999)
        self.request.groups = ()

    def get_app(self):
        return Webapp.objects.get(pk=337141)

    def get_data(self, **kwargs):
        default = {
            'app_slug': 'thisIsAslug',
            'description': '...',
            'privacy_policy': '...',
            'support_email': 'test@example.com',
            'notes': '',
            'publish_type': mkt.PUBLISH_IMMEDIATE,
        }
        default.update(kwargs)
        return default

    def test_slug(self):
        app = self.get_app()
        form = forms.AppDetailsBasicForm(self.get_data(), request=self.request,
                                         instance=app)
        assert form.is_valid(), form.errors
        form.save()
        eq_(app.app_slug, 'thisisaslug')

    def test_comm_thread(self):
        app = self.get_app()
        note_body = 'please approve this app'
        form = forms.AppDetailsBasicForm(self.get_data(notes=note_body),
                                         request=self.request, instance=app)
        assert form.is_valid(), form.errors
        form.save()
        notes = CommunicationNote.objects.all()
        eq_(notes.count(), 1)
        eq_(notes[0].body, note_body)

    def test_publish_type(self):
        app = self.get_app()
        form = forms.AppDetailsBasicForm(
            self.get_data(publish_type=mkt.PUBLISH_PRIVATE),
            request=self.request, instance=app)
        assert form.is_valid(), form.errors
        form.save()
        eq_(app.publish_type, mkt.PUBLISH_PRIVATE)

    def test_help_text_uses_safetext_and_includes_url(self):
        app = self.get_app()
        form = forms.AppDetailsBasicForm(
            self.get_data(publish_type=mkt.PUBLISH_PRIVATE),
            request=self.request, instance=app)

        help_text = form.base_fields['privacy_policy'].help_text
        eq_(type(help_text), SafeText)
        ok_('{url}' not in help_text)
        ok_(form.PRIVACY_MDN_URL in help_text)

    def test_is_offline_guess_false(self):
        app = self.get_app()
        app.guess_is_offline = lambda: False
        assert not app.is_offline
        forms.AppDetailsBasicForm(
            self.get_data(),
            request=self.request,
            instance=app)
        assert not app.is_offline

    def test_is_offline_guess_false_override(self):
        app = self.get_app()
        app.guess_is_offline = lambda: False
        form = forms.AppDetailsBasicForm(
            self.get_data(is_offline=True),
            request=self.request,
            instance=app)
        assert form.is_valid(), form.errors
        form.save()
        eq_(app.is_offline, True)

    def test_is_offline_guess_true(self):
        app = self.get_app()
        app.guess_is_offline = lambda: True
        assert not app.is_offline
        forms.AppDetailsBasicForm(
            self.get_data(is_offline=None),
            request=self.request,
            instance=app)
        assert app.is_offline

    def test_is_offline_guess_true_override(self):
        app = self.get_app()
        app.guess_is_offline = lambda: True
        form = forms.AppDetailsBasicForm(
            self.get_data(is_offline=False),
            request=self.request,
            instance=app)
        assert form.is_valid(), form.errors
        form.save()
        eq_(app.is_offline, False)

    def test_tags(self):
        app = self.get_app()
        form = forms.AppDetailsBasicForm(
            self.get_data(tags='card games, poker'), request=self.request,
            instance=app)
        assert form.is_valid(), form.errors
        form.save()
        eq_(app.tags.count(), 2)
        self.assertSetEqual(
            app.tags.values_list('tag_text', flat=True),
            ['card games', 'poker'])


class TestAppFeaturesForm(mkt.site.tests.TestCase):
    fixtures = fixture('user_999', 'webapp_337141')

    def setUp(self):
        mkt.set_user(UserProfile.objects.all()[0])
        self.form = forms.AppFeaturesForm()
        self.app = Webapp.objects.get(pk=337141)
        self.features = self.app.current_version.features

    def _check_log(self, action):
        assert AppLog.objects.filter(
            addon=self.app, activity_log__action=action.id).exists(), (
                "Didn't find `%s` action in logs." % action.short)

    def test_required(self):
        f_names = self.form.fields.keys()
        for value in (True, False):
            form = forms.AppFeaturesForm(dict((n, value) for n in f_names))
            eq_(form.is_valid(), True, form.errors)

    def test_correct_fields(self):
        fields = self.form.fields
        f_values = fields.values()
        assert 'version' not in fields
        assert all(isinstance(f, BooleanField) for f in f_values)
        self.assertSetEqual(fields, AppFeatures()._fields())

    def test_required_api_fields(self):
        fields = [f.help_text for f in self.form.required_api_fields()]
        eq_(fields, sorted(f['name'] for f in APP_FEATURES.values()))

    def test_required_api_fields_nonascii(self):
        forms.AppFeaturesForm.base_fields['has_apps'].help_text = _(
            u'H\xe9llo')
        fields = [f.help_text for f in self.form.required_api_fields()]
        eq_(fields, sorted(f['name'] for f in APP_FEATURES.values()))

    def test_changes_mark_for_rereview(self):
        self.features.update(has_sms=True)
        data = {'has_apps': True}
        self.form = forms.AppFeaturesForm(instance=self.features, data=data)
        self.form.save()
        ok_(self.features.has_apps)
        ok_(not self.features.has_sms)
        ok_(not self.features.has_contacts)
        action_id = mkt.LOG.REREVIEW_FEATURES_CHANGED.id
        assert AppLog.objects.filter(addon=self.app,
                                     activity_log__action=action_id).exists()
        eq_(RereviewQueue.objects.count(), 1)

    def test_no_changes_not_marked_for_rereview(self):
        self.features.update(has_sms=True)
        data = {'has_sms': True}
        self.form = forms.AppFeaturesForm(instance=self.features, data=data)
        self.form.save()
        ok_(not self.features.has_apps)
        ok_(self.features.has_sms)
        eq_(RereviewQueue.objects.count(), 0)
        action_id = mkt.LOG.REREVIEW_FEATURES_CHANGED.id
        assert not AppLog.objects.filter(
            addon=self.app,
            activity_log__action=action_id).exists()

    def test_changes_mark_for_rereview_bypass(self):
        self.features.update(has_sms=True)
        data = {'has_apps': True}
        self.form = forms.AppFeaturesForm(instance=self.features, data=data)
        self.form.save(mark_for_rereview=False)
        ok_(self.features.has_apps)
        ok_(not self.features.has_sms)
        eq_(RereviewQueue.objects.count(), 0)
        action_id = mkt.LOG.REREVIEW_FEATURES_CHANGED.id
        assert not AppLog.objects.filter(
            addon=self.app,
            activity_log__action=action_id).exists()
