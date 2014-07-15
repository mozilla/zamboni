# -*- coding: utf-8 -*-
import json
import os
import shutil

from django import forms as django_forms
from django.conf import settings
from django.core.files.storage import default_storage as storage
from django.core.files.uploadedfile import SimpleUploadedFile

import mock
from nose.tools import eq_, ok_
from test_utils import RequestFactory

import amo
import amo.tests
import mkt
from amo.tests import app_factory, version_factory
from amo.tests.test_helpers import get_image_path
from mkt.developers import forms
from mkt.developers.tests.test_views_edit import TestAdmin
from mkt.files.helpers import copyfileobj
from mkt.site.fixtures import fixture
from mkt.tags.models import Tag
from mkt.translations.models import Translation
from mkt.users.models import UserProfile
from mkt.webapps.models import Addon, Geodata, IARCInfo, Webapp


class TestPreviewForm(amo.tests.TestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        self.addon = Addon.objects.get(pk=337141)
        self.dest = os.path.join(settings.TMP_PATH, 'preview')
        if not os.path.exists(self.dest):
            os.makedirs(self.dest)

    @mock.patch('amo.models.ModelBase.update')
    def test_preview_modified(self, update_mock):
        name = 'transparent.png'
        form = forms.PreviewForm({'upload_hash': name,
                                  'position': 1})
        shutil.copyfile(get_image_path(name), os.path.join(self.dest, name))
        assert form.is_valid(), form.errors
        form.save(self.addon)
        assert update_mock.called

    def test_preview_size(self):
        name = 'non-animated.gif'
        form = forms.PreviewForm({'upload_hash': name,
                                  'position': 1})
        with storage.open(os.path.join(self.dest, name), 'wb') as f:
            copyfileobj(open(get_image_path(name)), f)
        assert form.is_valid(), form.errors
        form.save(self.addon)
        eq_(self.addon.previews.all()[0].sizes,
            {u'image': [250, 297], u'thumbnail': [100, 119]})

    def check_file_type(self, type_):
        form = forms.PreviewForm({'upload_hash': type_,
                                  'position': 1})
        assert form.is_valid(), form.errors
        form.save(self.addon)
        return self.addon.previews.all()[0].filetype

    @mock.patch('lib.video.tasks.resize_video')
    def test_preview_good_file_type(self, resize_video):
        eq_(self.check_file_type('x.video-webm'), 'video/webm')

    def test_preview_other_file_type(self):
        eq_(self.check_file_type('x'), 'image/png')

    def test_preview_bad_file_type(self):
        eq_(self.check_file_type('x.foo'), 'image/png')


class TestCategoryForm(amo.tests.WebappTestCase):
    fixtures = fixture('user_999', 'webapp_337141')

    def setUp(self):
        super(TestCategoryForm, self).setUp()
        self.user = UserProfile.objects.get(username='regularuser')
        self.app = Webapp.objects.get(pk=337141)
        self.request = RequestFactory()
        self.request.user = self.user
        self.request.groups = ()
        self.cat = 'social'

    def _make_form(self, data=None):
        self.form = forms.CategoryForm(
            data, product=self.app, request=self.request)

    def test_has_no_cats(self):
        self._make_form()
        eq_(self.form.initial['categories'], [])
        eq_(self.form.max_categories(), 2)

    def test_save_cats(self):
        self._make_form({'categories': ['books', 'social']})
        assert self.form.is_valid(), self.form.errors
        self.form.save()
        eq_(self.app.reload().categories, ['books', 'social'])
        eq_(self.form.max_categories(), 2)

    def test_save_too_many_cats(self):
        self._make_form({'categories': ['books', 'social', 'games']})
        ok_(self.form.errors)

    def test_save_non_existent_cat(self):
        self._make_form({'categories': ['nonexistent']})
        ok_(self.form.errors)


class TestRegionForm(amo.tests.WebappTestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        super(TestRegionForm, self).setUp()
        self.request = RequestFactory()
        self.kwargs = {'product': self.app}

    def test_initial_checked(self):
        form = forms.RegionForm(data=None, **self.kwargs)
        # Even special regions (i.e., China) should be checked.
        self.assertSetEqual(form.initial['regions'],
            set(mkt.regions.ALL_REGION_IDS))
        eq_(form.initial['enable_new_regions'], False)

    def test_initial_excluded_in_region(self):
        self.app.addonexcludedregion.create(region=mkt.regions.BR.id)

        # Everything except Brazil.
        regions = set(mkt.regions.ALL_REGION_IDS)
        regions.remove(mkt.regions.BR.id)
        self.assertSetEqual(self.get_app().get_region_ids(restofworld=True),
            regions)

        form = forms.RegionForm(data=None, **self.kwargs)

        # Everything (even China) except Brazil.
        self.assertSetEqual(form.initial['regions'], regions)
        eq_(form.initial['enable_new_regions'], False)

    def test_initial_excluded_in_regions_and_future_regions(self):
        regions = [mkt.regions.BR, mkt.regions.UK, mkt.regions.RESTOFWORLD]
        for region in regions:
            self.app.addonexcludedregion.create(region=region.id)

        regions = set(mkt.regions.ALL_REGION_IDS)
        regions.remove(mkt.regions.BR.id)
        regions.remove(mkt.regions.UK.id)
        regions.remove(mkt.regions.RESTOFWORLD.id)

        self.assertSetEqual(self.get_app().get_region_ids(),
            regions)

        form = forms.RegionForm(data=None, **self.kwargs)
        self.assertSetEqual(form.initial['regions'], regions)
        eq_(form.initial['enable_new_regions'], False)

    def test_restofworld_only(self):
        form = forms.RegionForm({'regions': [mkt.regions.RESTOFWORLD.id]},
                                **self.kwargs)
        assert form.is_valid(), form.errors

    def test_no_regions(self):
        form = forms.RegionForm({'enable_new_regions': True}, **self.kwargs)
        assert not form.is_valid(), 'Form should be invalid'
        eq_(form.errors,
            {'regions': ['You must select at least one region.']})

    def test_exclude_each_region(self):
        """Test that it's possible to exclude each region."""

        for region_id in mkt.regions.ALL_REGION_IDS:
            to_exclude = list(mkt.regions.ALL_REGION_IDS)
            to_exclude.remove(region_id)

            form = forms.RegionForm({'regions': to_exclude,
                                     'restricted': '1',
                                     'enable_new_regions': True},
                                    **self.kwargs)
            assert form.is_valid(), form.errors
            form.save()

            r_id = mkt.regions.REGIONS_CHOICES_ID_DICT[region_id]
            eq_(self.app.reload().get_region_ids(True), to_exclude,
                'Failed for %s' % r_id)

    def test_exclude_restofworld(self):
        form = forms.RegionForm({'regions': mkt.regions.REGION_IDS,
                                 'restricted': '1',
                                 'enable_new_regions': False}, **self.kwargs)
        assert form.is_valid(), form.errors
        form.save()
        eq_(self.app.get_region_ids(True), mkt.regions.REGION_IDS)

    def test_reinclude_region(self):
        self.app.addonexcludedregion.create(region=mkt.regions.BR.id)

        form = forms.RegionForm({'regions': mkt.regions.ALL_REGION_IDS,
                                 'enable_new_regions': True}, **self.kwargs)
        assert form.is_valid(), form.errors
        form.save()
        eq_(self.app.get_region_ids(True), mkt.regions.ALL_REGION_IDS)

    def test_reinclude_restofworld(self):
        self.app.addonexcludedregion.create(
                region=mkt.regions.RESTOFWORLD.id)

        form = forms.RegionForm({'regions': mkt.regions.ALL_REGION_IDS},
                                **self.kwargs)
        assert form.is_valid(), form.errors
        form.save()
        eq_(self.app.get_region_ids(True), mkt.regions.ALL_REGION_IDS)

    def test_restofworld_valid_choice_paid(self):
        self.app.update(premium_type=amo.ADDON_PREMIUM)
        form = forms.RegionForm(
            {'regions': [mkt.regions.RESTOFWORLD.id]}, **self.kwargs)
        assert form.is_valid(), form.errors

    def test_restofworld_valid_choice_free(self):
        form = forms.RegionForm(
            {'regions': [mkt.regions.RESTOFWORLD.id]}, **self.kwargs)
        assert form.is_valid(), form.errors

    def test_china_initially_included(self):
        self.create_flag('special-regions')
        form = forms.RegionForm(None, **self.kwargs)
        cn = mkt.regions.CN.id
        assert cn in form.initial['regions']
        assert cn in dict(form.fields['regions'].choices).keys()

    def _test_china_excluded_if_pending_or_rejected(self):
        self.create_flag('special-regions')

        # Mark app as pending/rejected in China.
        for status in (amo.STATUS_PENDING, amo.STATUS_REJECTED):
            self.app.geodata.set_status(mkt.regions.CN, status, save=True)
            eq_(self.app.geodata.get_status(mkt.regions.CN), status)

            # Post the form.
            form = forms.RegionForm({'regions': mkt.regions.ALL_REGION_IDS,
                                     'special_regions': [mkt.regions.CN.id]},
                                    **self.kwargs)

            # China should be checked if it's pending and
            # unchecked if rejected.
            cn = mkt.regions.CN.id
            if status == amo.STATUS_PENDING:
                assert cn in form.initial['regions'], (
                    status, form.initial['regions'])
            else:
                assert cn not in form.initial['regions'], (
                    status, form.initial['regions'])
            choices = dict(form.fields['regions'].choices).keys()
            assert cn in choices, (status, choices)

            assert form.is_valid(), form.errors
            form.save()

            # App should be unlisted in China and always pending after
            # requesting China.
            self.app = self.app.reload()
            eq_(self.app.listed_in(mkt.regions.CN), False)
            eq_(self.app.geodata.get_status(mkt.regions.CN),
                amo.STATUS_PENDING)

    def test_china_excluded_if_pending_or_rejected(self):
        self._test_china_excluded_if_pending_or_rejected()

    def test_china_already_excluded_and_pending_or_rejected(self):
        cn = mkt.regions.CN.id
        self.app.addonexcludedregion.create(region=cn)

        # If the app was already excluded in China, the checkbox should still
        # be checked if the app's been requested for approval in China now.
        self._test_china_excluded_if_pending_or_rejected()

    def test_china_excluded_if_pending_cancelled(self):
        """
        If the developer already requested to be in China,
        and a reviewer hasn't reviewed it for China yet,
        keep the region exclusion and the status as pending.

        """

        self.create_flag('special-regions')

        # Mark app as pending in China.
        status = amo.STATUS_PENDING
        self.app.geodata.set_status(mkt.regions.CN, status, save=True)
        eq_(self.app.geodata.get_status(mkt.regions.CN), status)

        # Post the form.
        form = forms.RegionForm({'regions': mkt.regions.ALL_REGION_IDS},
                                **self.kwargs)

        # China should be checked if it's pending.
        cn = mkt.regions.CN.id
        assert cn in form.initial['regions']
        assert cn in dict(form.fields['regions'].choices).keys()

        assert form.is_valid(), form.errors
        form.save()

        # App should be unlisted in China and now null.
        self.app = self.app.reload()
        eq_(self.app.listed_in(mkt.regions.CN), False)
        eq_(self.app.geodata.get_status(mkt.regions.CN), amo.STATUS_NULL)

    def test_china_included_if_approved_but_unchecked(self):
        self.create_flag('special-regions')

        # Mark app as public in China.
        status = amo.STATUS_PUBLIC
        self.app.geodata.set_status(mkt.regions.CN, status, save=True)
        eq_(self.app.geodata.get_status(mkt.regions.CN), status)

        # Post the form.
        form = forms.RegionForm({'regions': mkt.regions.ALL_REGION_IDS},
                                **self.kwargs)

        # China should be checked if it's public.
        cn = mkt.regions.CN.id
        assert cn in form.initial['regions']
        assert cn in dict(form.fields['regions'].choices).keys()

        assert form.is_valid(), form.errors
        form.save()

        # App should be unlisted in China and now null.
        self.app = self.app.reload()
        eq_(self.app.listed_in(mkt.regions.CN), False)
        eq_(self.app.geodata.get_status(mkt.regions.CN), amo.STATUS_NULL)

    def test_china_included_if_approved_and_checked(self):
        self.create_flag('special-regions')

        # Mark app as public in China.
        status = amo.STATUS_PUBLIC
        self.app.geodata.set_status(mkt.regions.CN, status, save=True)
        eq_(self.app.geodata.get_status(mkt.regions.CN), status)

        # Post the form.
        form = forms.RegionForm({'regions': mkt.regions.ALL_REGION_IDS,
                                 'special_regions': [mkt.regions.CN.id]},
                                **self.kwargs)
        assert form.is_valid(), form.errors
        form.save()

        # App should still be listed in China and still public.
        self.app = self.app.reload()
        eq_(self.app.listed_in(mkt.regions.CN), True)
        eq_(self.app.geodata.get_status(mkt.regions.CN), status)


class TestNewManifestForm(amo.tests.TestCase):

    @mock.patch('mkt.developers.forms.verify_app_domain')
    def test_normal_validator(self, _verify_app_domain):
        form = forms.NewManifestForm({'manifest': 'http://omg.org/yes.webapp'},
            is_standalone=False)
        assert form.is_valid()
        assert _verify_app_domain.called

    @mock.patch('mkt.developers.forms.verify_app_domain')
    def test_standalone_validator(self, _verify_app_domain):
        form = forms.NewManifestForm({'manifest': 'http://omg.org/yes.webapp'},
            is_standalone=True)
        assert form.is_valid()
        assert not _verify_app_domain.called


class TestPackagedAppForm(amo.tests.AMOPaths, amo.tests.WebappTestCase):

    def setUp(self):
        super(TestPackagedAppForm, self).setUp()
        path = self.packaged_app_path('mozball.zip')
        self.files = {'upload': SimpleUploadedFile('mozball.zip',
                                                   open(path).read())}

    def test_not_there(self):
        form = forms.NewPackagedAppForm({}, {})
        assert not form.is_valid()
        eq_(form.errors['upload'], [u'This field is required.'])
        eq_(form.file_upload, None)

    def test_right_size(self):
        form = forms.NewPackagedAppForm({}, self.files)
        assert form.is_valid(), form.errors
        assert form.file_upload

    def test_too_big(self):
        form = forms.NewPackagedAppForm({}, self.files, max_size=5)
        assert not form.is_valid()
        validation = json.loads(form.file_upload.validation)
        assert 'messages' in validation, 'No messages in validation.'
        eq_(validation['messages'][0]['message'],
            u'Packaged app too large for submission. Packages must be smaller '
            u'than 5 bytes.')

    def test_origin_exists(self):
        self.app.update(app_domain='app://hy.fr')
        form = forms.NewPackagedAppForm({}, self.files)
        assert not form.is_valid()
        validation = json.loads(form.file_upload.validation)
        eq_(validation['messages'][0]['message'],
            'An app already exists on this domain; only one app per domain is '
            'allowed.')


class TestTransactionFilterForm(amo.tests.TestCase):

    def setUp(self):
        (app_factory(), app_factory())
        # Need queryset to initialize form.
        self.apps = Webapp.objects.all()
        self.data = {
            'app': self.apps[0].id,
            'transaction_type': 1,
            'transaction_id': 1,
            'date_from_day': '1',
            'date_from_month': '1',
            'date_from_year': '2012',
            'date_to_day': '1',
            'date_to_month': '1',
            'date_to_year': '2013',
        }

    def test_basic(self):
        """Test the form doesn't crap out."""
        form = forms.TransactionFilterForm(self.data, apps=self.apps)
        assert form.is_valid(), form.errors

    def test_app_choices(self):
        """Test app choices."""
        form = forms.TransactionFilterForm(self.data, apps=self.apps)
        for app in self.apps:
            assertion = (app.id, app.name) in form.fields['app'].choices
            assert assertion, '(%s, %s) not in choices' % (app.id, app.name)


class TestAppFormBasic(amo.tests.TestCase):

    def setUp(self):
        self.data = {
            'slug': 'yolo',
            'manifest_url': 'https://omg.org/yes.webapp',
            'description': 'You Only Live Once'
        }
        self.request = mock.Mock()
        self.request.groups = ()

    def post(self):
        self.form = forms.AppFormBasic(
            self.data, instance=Webapp.objects.create(app_slug='yolo'),
            request=self.request)

    def test_success(self):
        self.post()
        eq_(self.form.is_valid(), True, self.form.errors)
        eq_(self.form.errors, {})

    def test_slug_invalid(self):
        Webapp.objects.create(app_slug='yolo')
        self.post()
        eq_(self.form.is_valid(), False)
        eq_(self.form.errors,
            {'slug': ['This slug is already in use. Please choose another.']})


class TestAppVersionForm(amo.tests.TestCase):

    def setUp(self):
        self.request = mock.Mock()
        self.app = app_factory(publish_type=amo.PUBLISH_IMMEDIATE,
                               version_kw={'version': '1.0',
                                           'created': self.days_ago(5)})
        version_factory(addon=self.app, version='2.0',
                        file_kw=dict(status=amo.STATUS_PENDING))
        self.app.reload()

    def _get_form(self, version, data=None):
        return forms.AppVersionForm(data, instance=version)

    def test_get_publish(self):
        form = self._get_form(self.app.latest_version)
        eq_(form.fields['publish_immediately'].initial, True)

        self.app.update(publish_type=amo.PUBLISH_PRIVATE)
        self.app.reload()
        form = self._get_form(self.app.latest_version)
        eq_(form.fields['publish_immediately'].initial, False)

    def test_post_publish(self):
        # Using the latest_version, which is pending.
        form = self._get_form(self.app.latest_version,
                             data={'publish_immediately': True})
        eq_(form.is_valid(), True)
        form.save()
        self.app.reload()
        eq_(self.app.publish_type, amo.PUBLISH_IMMEDIATE)

        form = self._get_form(self.app.latest_version,
                             data={'publish_immediately': False})
        eq_(form.is_valid(), True)
        form.save()
        self.app.reload()
        eq_(self.app.publish_type, amo.PUBLISH_PRIVATE)

    def test_post_publish_not_pending(self):
        # Using the current_version, which is public.
        form = self._get_form(self.app.current_version,
                             data={'publish_immediately': False})
        eq_(form.is_valid(), True)
        form.save()
        self.app.reload()
        eq_(self.app.publish_type, amo.PUBLISH_IMMEDIATE)


class TestAdminSettingsForm(TestAdmin):

    def setUp(self):
        super(TestAdminSettingsForm, self).setUp()
        self.data = {'position': 1}
        self.user = UserProfile.objects.get(username='admin')
        self.request = RequestFactory()
        self.request.user = self.user
        self.request.groups = ()
        self.kwargs = {'instance': self.webapp, 'request': self.request}

    @mock.patch('mkt.developers.forms.index_webapps.delay')
    def test_reindexed(self, index_webapps_mock):
        form = forms.AdminSettingsForm(self.data, **self.kwargs)
        assert form.is_valid(), form.errors
        form.save(self.webapp)
        index_webapps_mock.assert_called_with([self.webapp.id])

    def test_adding_tags(self):
        self.data.update({'tags': 'tag one, tag two'})
        form = forms.AdminSettingsForm(self.data, **self.kwargs)
        assert form.is_valid(), form.errors
        form.save(self.webapp)

        eq_(self.webapp.tags.count(), 2)
        self.assertSetEqual(
            self.webapp.tags.values_list('tag_text', flat=True),
            ['tag one', 'tag two'])

    def test_removing_tags(self):
        Tag(tag_text='tag one').save_tag(self.webapp)
        eq_(self.webapp.tags.count(), 1)

        self.data.update({'tags': 'tag two, tag three'})
        form = forms.AdminSettingsForm(self.data, **self.kwargs)
        assert form.is_valid(), form.errors
        form.save(self.webapp)

        eq_(self.webapp.tags.count(), 2)
        self.assertSetEqual(
            self.webapp.tags.values_list('tag_text', flat=True),
            ['tag two', 'tag three'])

    def test_removing_all_tags(self):
        Tag(tag_text='tag one').save_tag(self.webapp)
        eq_(self.webapp.tags.count(), 1)

        self.data.update({'tags': ''})
        form = forms.AdminSettingsForm(self.data, **self.kwargs)
        assert form.is_valid(), form.errors
        form.save(self.webapp)

        eq_(self.webapp.tags.count(), 0)
        self.assertSetEqual(
            self.webapp.tags.values_list('tag_text', flat=True), [])

    def test_banner_message(self):
        self.data.update({
            'banner_message_en-us': u'Oh Hai.',
            'banner_message_es': u'¿Dónde está la biblioteca?',
        })
        form = forms.AdminSettingsForm(self.data, **self.kwargs)
        assert form.is_valid(), form.errors
        form.save(self.webapp)

        geodata = self.webapp.geodata.reload()
        trans_id = geodata.banner_message_id
        eq_(geodata.banner_message, self.data['banner_message_en-us'])
        eq_(unicode(Translation.objects.get(id=trans_id, locale='es')),
            self.data['banner_message_es'])
        eq_(unicode(Translation.objects.get(id=trans_id, locale='en-us')),
           self.data['banner_message_en-us'])

    def test_banner_regions_garbage(self):
        self.data.update({
            'banner_regions': ['LOL']
        })
        form = forms.AdminSettingsForm(self.data, **self.kwargs)
        assert not form.is_valid(), form.errors

    def test_banner_regions_valid(self):  # Use strings
        self.data.update({
            'banner_regions': [unicode(mkt.regions.BR.id),
                               mkt.regions.SPAIN.id]
        })
        self.webapp.geodata.update(banner_regions=[mkt.regions.RS.id])
        form = forms.AdminSettingsForm(self.data, **self.kwargs)
        eq_(form.initial['banner_regions'], [mkt.regions.RS.id])
        assert form.is_valid(), form.errors
        eq_(form.cleaned_data['banner_regions'], [mkt.regions.BR.id,
                                                  mkt.regions.SPAIN.id])
        form.save(self.webapp)
        geodata = self.webapp.geodata.reload()
        eq_(geodata.banner_regions, [mkt.regions.BR.id, mkt.regions.SPAIN.id])

    def test_banner_regions_initial(self):
        form = forms.AdminSettingsForm(self.data, **self.kwargs)
        eq_(self.webapp.geodata.banner_regions, None)
        eq_(form.initial['banner_regions'], [])

        self.webapp.geodata.update(banner_regions=[])
        form = forms.AdminSettingsForm(self.data, **self.kwargs)
        eq_(form.initial['banner_regions'], [])


class TestIARCGetAppInfoForm(amo.tests.WebappTestCase):

    def _get_form(self, app=None, **kwargs):
        data = {
            'submission_id': 1,
            'security_code': 'a'
        }
        data.update(kwargs)
        return forms.IARCGetAppInfoForm(data=data, app=app or self.app)

    @mock.patch('mkt.webapps.models.Webapp.set_iarc_storefront_data')
    def test_good(self, storefront_mock):
        with self.assertRaises(IARCInfo.DoesNotExist):
            self.app.iarc_info

        form = self._get_form()
        assert form.is_valid(), form.errors
        form.save()

        iarc_info = IARCInfo.objects.get(addon=self.app)
        eq_(iarc_info.submission_id, 1)
        eq_(iarc_info.security_code, 'a')
        assert storefront_mock.called

    @mock.patch.object(settings, 'IARC_ALLOW_CERT_REUSE', False)
    def test_iarc_cert_reuse_on_self(self):
        # Test okay to use on self.
        self.app.set_iarc_info(1, 'a')
        form = self._get_form()
        ok_(form.is_valid())
        form.save()
        eq_(IARCInfo.objects.count(), 1)

    @mock.patch.object(settings, 'IARC_ALLOW_CERT_REUSE', False)
    def test_iarc_cert_already_used(self):
        # Test okay to use on self.
        self.app.set_iarc_info(1, 'a')
        eq_(IARCInfo.objects.count(), 1)

        some_app = amo.tests.app_factory()
        form = self._get_form(app=some_app)
        ok_(not form.is_valid())

        form = self._get_form(app=some_app, submission_id=2)
        ok_(form.is_valid())

    @mock.patch.object(settings, 'IARC_ALLOW_CERT_REUSE', True)
    def test_iarc_already_used_dev(self):
        self.app.set_iarc_info(1, 'a')
        form = self._get_form()
        ok_(form.is_valid())

    @mock.patch('mkt.webapps.models.Webapp.set_iarc_storefront_data')
    def test_changing_cert(self, storefront_mock):
        self.app.set_iarc_info(1, 'a')
        form = self._get_form(submission_id=2, security_code='b')
        ok_(form.is_valid(), form.errors)
        form.save()

        iarc_info = self.app.iarc_info.reload()
        eq_(iarc_info.submission_id, 2)
        eq_(iarc_info.security_code, 'b')
        assert storefront_mock.called

    def test_iarc_unexclude(self):
        geodata, created = Geodata.objects.get_or_create(addon=self.app)
        geodata.update(region_br_iarc_exclude=True,
                       region_de_iarc_exclude=True)

        form = self._get_form()
        ok_(form.is_valid())
        form.save()

        geodata = Geodata.objects.get(addon=self.app)
        assert not geodata.region_br_iarc_exclude
        assert not geodata.region_de_iarc_exclude

    def test_allow_subm(self):
        form = self._get_form(submission_id='subm-1231')
        assert form.is_valid(), form.errors
        form.save()

        iarc_info = self.app.iarc_info
        eq_(iarc_info.submission_id, 1231)
        eq_(iarc_info.security_code, 'a')

    @mock.patch('mkt.webapps.models.Webapp.set_iarc_storefront_data')
    def test_bad_submission_id(self, storefront_mock):
        form = self._get_form(submission_id='subwayeatfresh-133')
        assert not form.is_valid()
        assert not storefront_mock.called

    @mock.patch('mkt.webapps.models.Webapp.set_iarc_storefront_data')
    def test_incomplete(self, storefront_mock):
        form = self._get_form(submission_id=None)
        assert not form.is_valid(), 'Form was expected to be invalid.'
        assert not storefront_mock.called

    @mock.patch('lib.iarc.utils.IARC_XML_Parser.parse_string')
    def test_rating_not_found(self, _mock):
        _mock.return_value = {'rows': [
            {'ActionStatus': 'No records found. Please try another criteria.'}
        ]}
        form = self._get_form()
        assert form.is_valid(), form.errors
        with self.assertRaises(django_forms.ValidationError):
            form.save()
