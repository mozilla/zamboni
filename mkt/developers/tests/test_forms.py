# -*- coding: utf-8 -*-
import json
import os
import shutil
import uuid

from django import forms as django_forms
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test.client import RequestFactory
from django.test.utils import override_settings

import mock
from nose.tools import eq_, ok_

import mkt
import mkt.site.tests
from lib.iarc_v2.client import IARCException
from lib.post_request_task import task as post_request_task
from mkt.constants import ratingsbodies
from mkt.developers import forms
from mkt.developers.tests.test_views_edit import TestAdmin
from mkt.site.fixtures import fixture
from mkt.site.storage_utils import (copy_stored_file, local_storage,
                                    private_storage)
from mkt.site.tests.test_utils_ import get_image_path
from mkt.site.utils import app_factory, version_factory
from mkt.tags.models import Tag
from mkt.users.models import UserProfile
from mkt.webapps.models import Geodata, IARCCert, IARCInfo, Webapp


class TestPreviewForm(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141', 'user_999')

    def setUp(self):
        self.addon = Webapp.objects.get(pk=337141)
        self.dest = os.path.join(settings.TMP_PATH, 'preview')
        self.user = UserProfile.objects.get(pk=999)
        mkt.set_user(self.user)
        if not os.path.exists(self.dest):
            os.makedirs(self.dest)

    @mock.patch('mkt.site.models.ModelBase.update')
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
        form = forms.PreviewForm({'upload_hash': name, 'position': 1})
        copy_stored_file(
            get_image_path(name), os.path.join(self.dest, name),
            src_storage=local_storage, dst_storage=private_storage)
        assert form.is_valid(), form.errors
        form.save(self.addon)
        # Since the task is a post-request-task and we are outside the normal
        # request-response cycle, manually send the tasks.
        post_request_task._send_tasks()
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


class TestCategoryForm(mkt.site.tests.WebappTestCase):
    fixtures = fixture('user_999', 'webapp_337141')

    def setUp(self):
        super(TestCategoryForm, self).setUp()
        self.user = UserProfile.objects.get(email='regular@mozilla.com')
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
        self._make_form({'categories': ['books-comics', 'social']})
        assert self.form.is_valid(), self.form.errors
        self.form.save()
        eq_(self.app.reload().categories, ['books-comics', 'social'])
        eq_(self.form.max_categories(), 2)

    def test_save_too_many_cats(self):
        self._make_form({'categories': ['books-comics', 'social', 'games']})
        ok_(self.form.errors)

    def test_save_non_existent_cat(self):
        self._make_form({'categories': ['nonexistent']})
        ok_(self.form.errors)


@mock.patch('mkt.webapps.models.clean_memoized_exclusions', None)
class TestRegionForm(mkt.site.tests.WebappTestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        super(TestRegionForm, self).setUp()
        self.request = RequestFactory()
        self.kwargs = {'product': self.app}

    def test_initial_checked(self):
        form = forms.RegionForm(data=None, **self.kwargs)
        eq_(form.initial['restricted'], False)
        eq_(form.initial['enable_new_regions'], True)
        self.assertSetEqual(form.initial['regions'],
                            set(mkt.regions.ALL_REGION_IDS))

    def test_initial_excluded_in_region(self):
        self.app.geodata.update(restricted=True)
        self.app.update(enable_new_regions=False)
        self.app.addonexcludedregion.create(region=mkt.regions.BRA.id)

        # Everything except Brazil.
        regions = set(mkt.regions.ALL_REGION_IDS)
        regions.remove(mkt.regions.BRA.id)
        self.assertSetEqual(self.get_app().get_region_ids(restofworld=True),
                            regions)

        form = forms.RegionForm(data=None, **self.kwargs)

        # Everything except Brazil.
        self.assertSetEqual(form.initial['regions'], regions)
        eq_(form.initial['enable_new_regions'], False)

    def test_initial_excluded_in_regions_and_future_regions(self):
        self.app.geodata.update(restricted=True)
        self.app.update(enable_new_regions=False)
        regions = [mkt.regions.BRA, mkt.regions.GBR, mkt.regions.RESTOFWORLD]
        for region in regions:
            self.app.addonexcludedregion.create(region=region.id)

        regions = set(mkt.regions.ALL_REGION_IDS)
        regions.remove(mkt.regions.BRA.id)
        regions.remove(mkt.regions.GBR.id)
        regions.remove(mkt.regions.RESTOFWORLD.id)

        self.assertSetEqual(self.get_app().get_region_ids(),
                            regions)

        form = forms.RegionForm(data=None, **self.kwargs)
        self.assertSetEqual(form.initial['regions'], regions)
        eq_(form.initial['enable_new_regions'], False)

    def test_restricted_ignores_enable_new_regions(self):
        self.app.geodata.update(restricted=True)
        self.app.update(enable_new_regions=False)

        form = forms.RegionForm({'restricted': '0',
                                 'regions': [mkt.regions.RESTOFWORLD.id],
                                 'enable_new_regions': False}, **self.kwargs)
        assert form.is_valid(), form.errors
        form.save()

        eq_(self.app.enable_new_regions, True)
        eq_(self.app.geodata.restricted, False)

    def test_restofworld_only(self):
        form = forms.RegionForm({'regions': [mkt.regions.RESTOFWORLD.id]},
                                **self.kwargs)
        assert form.is_valid(), form.errors

    def test_no_regions(self):
        form = forms.RegionForm({'restricted': '1',
                                 'enable_new_regions': True}, **self.kwargs)
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
        self.app.addonexcludedregion.create(region=mkt.regions.BRA.id)

        form = forms.RegionForm({'regions': mkt.regions.ALL_REGION_IDS,
                                 'enable_new_regions': True}, **self.kwargs)
        assert form.is_valid(), form.errors
        form.save()
        eq_(self.app.get_region_ids(True), mkt.regions.ALL_REGION_IDS)

    def test_reinclude_restofworld(self):
        self.app.addonexcludedregion.create(region=mkt.regions.RESTOFWORLD.id)

        form = forms.RegionForm({'restricted': '1',
                                 'regions': mkt.regions.ALL_REGION_IDS},
                                **self.kwargs)
        assert form.is_valid(), form.errors
        form.save()
        eq_(self.app.get_region_ids(True), mkt.regions.ALL_REGION_IDS)

    def test_restofworld_valid_choice_paid(self):
        self.app.update(premium_type=mkt.ADDON_PREMIUM)
        form = forms.RegionForm(
            {'restricted': '1',
             'regions': [mkt.regions.RESTOFWORLD.id]}, **self.kwargs)
        assert form.is_valid(), form.errors

    def test_paid_app_options_initial(self):
        """Check initial regions of a paid app post-save.

        Check that if we save the region form for a paid app
        with a specific region that should *not* be excluded it is still
        shown as a initial region when the new form instance is created.

        """

        self.app.update(premium_type=mkt.ADDON_PREMIUM)
        form = forms.RegionForm(
            {'restricted': '1',
             'regions': [mkt.regions.RESTOFWORLD.id]}, **self.kwargs)
        assert form.is_valid(), form.errors
        form.save()
        new_form = forms.RegionForm(**self.kwargs)
        self.assertIn(mkt.regions.RESTOFWORLD.id,
                      new_form.initial.get('regions', []))

    def test_restofworld_valid_choice_free(self):
        form = forms.RegionForm(
            {'restricted': '1',
             'regions': [mkt.regions.RESTOFWORLD.id]}, **self.kwargs)
        assert form.is_valid(), form.errors


class TestNewManifestForm(mkt.site.tests.TestCase):

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


class TestPackagedAppForm(mkt.site.tests.MktPaths,
                          mkt.site.tests.WebappTestCase):

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
            u'than 5\xa0bytes.')

    def test_origin_exists(self):
        self.app.update(app_domain='app://hy.fr')
        form = forms.NewPackagedAppForm({}, self.files)
        assert not form.is_valid()
        validation = json.loads(form.file_upload.validation)
        eq_(validation['messages'][0]['message'],
            'An app already exists on this domain; only one app per domain is '
            'allowed.')


class TestTransactionFilterForm(mkt.site.tests.TestCase):

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


class TestAppFormBasic(mkt.site.tests.TestCase):
    def setUp(self):
        self.data = {
            'slug': 'yolo',
            'manifest_url': 'https://omg.org/yes.webapp',
            'description': 'You Only Live Once'
        }
        self.user = mkt.site.tests.user_factory()
        self.request = mkt.site.tests.req_factory_factory(user=self.user)
        self.app = app_factory(name='YOLO',
                               manifest_url='https://omg.org/yes.webapp')

    def post(self, app=None):
        self.form = forms.AppFormBasic(self.data, instance=app or self.app,
                                       request=self.request)

    def test_success(self):
        self.post()
        eq_(self.form.is_valid(), True, self.form.errors)
        eq_(self.form.errors, {})

    def test_slug_invalid(self):
        app = Webapp.objects.create(app_slug='yolo')
        self.post(app=app)
        eq_(self.form.is_valid(), False)
        eq_(self.form.errors,
            {'slug': ['This slug is already in use. Please choose another.']})

    def test_adding_tags(self):
        self.data.update({'tags': 'tag one, tag two'})
        self.post()
        assert self.form.is_valid(), self.form.errors
        self.form.save(self.app)

        eq_(self.app.tags.count(), 2)
        self.assertSetEqual(
            self.app.tags.values_list('tag_text', flat=True),
            ['tag one', 'tag two'])

    def test_removing_tags(self):
        Tag(tag_text='tag one').save_tag(self.app)
        eq_(self.app.tags.count(), 1)

        self.data.update({'tags': 'tag two, tag three'})
        self.post()
        assert self.form.is_valid(), self.form.errors
        self.form.save(self.app)

        eq_(self.app.tags.count(), 2)
        self.assertSetEqual(
            self.app.tags.values_list('tag_text', flat=True),
            ['tag two', 'tag three'])

    def test_removing_all_tags(self):
        Tag(tag_text='tag one').save_tag(self.app)
        eq_(self.app.tags.count(), 1)

        self.data.update({'tags': ''})
        self.post()
        assert self.form.is_valid(), self.form.errors
        self.form.save(self.app)

        eq_(self.app.tags.count(), 0)
        self.assertSetEqual(
            self.app.tags.values_list('tag_text', flat=True), [])

    def test_add_restricted_tag_no_perm(self):
        Tag.objects.create(tag_text='restricted', restricted=True)
        self.data.update({'tags': 'restricted'})

        self.post()
        ok_(not self.form.is_valid())

    def test_add_restricted_tag_ok(self):
        Tag.objects.create(tag_text='restricted', restricted=True)
        self.data.update({'tags': 'restricted'})

        self.grant_permission(self.user, 'Apps:Edit')
        self.request = mkt.site.tests.req_factory_factory(user=self.user)

        self.post()
        assert self.form.is_valid(), self.form.errors

        self.form.save(self.app)
        self.assertSetEqual(self.app.tags.values_list('tag_text', flat=True),
                            ['restricted'])

    def test_add_restricted_tag_curator(self):
        Tag.objects.create(tag_text='restricted', restricted=True)
        self.data.update({'tags': 'restricted'})

        self.grant_permission(self.user, 'Feed:Curate')
        self.request = mkt.site.tests.req_factory_factory(user=self.user)

        self.post()
        assert self.form.is_valid(), self.form.errors

        self.form.save(self.app)
        self.assertSetEqual(self.app.tags.values_list('tag_text', flat=True),
                            ['restricted'])

    def test_restricted_tag_not_removed(self):
        t = Tag.objects.create(tag_text='restricted', restricted=True)
        self.app.tags.add(t)
        self.data.update({'tags': 'hey'})

        self.post()
        assert self.form.is_valid(), self.form.errors
        self.form.save(self.app)

        ok_(self.app.tags.filter(tag_text='restricted'))
        ok_(self.app.tags.filter(tag_text='hey'))

    def test_remove_restricted_tag_with_perms(self):
        t = Tag.objects.create(tag_text='restricted', restricted=True)
        self.app.tags.add(t)
        self.data.update({'tags': 'hey'})

        self.grant_permission(self.user, 'Apps:Edit')
        self.request = mkt.site.tests.req_factory_factory(user=self.user)

        self.post()
        assert self.form.is_valid(), self.form.errors
        self.form.save(self.app)

        ok_(not self.app.tags.filter(tag_text='restricted'))
        ok_(self.app.tags.filter(tag_text='hey'))

    @mock.patch('mkt.developers.forms.update_manifests')
    def test_manifest_url_change(self, mock):
        self.data.update({'manifest_url': 'https://omg.org/no.webapp'})
        self.post()
        assert self.form.is_valid(), self.form.errors
        self.form.save(self.app)
        assert mock.delay.called


class TestAppVersionForm(mkt.site.tests.TestCase):

    def setUp(self):
        self.request = mock.Mock()
        self.app = app_factory(publish_type=mkt.PUBLISH_IMMEDIATE,
                               version_kw={'version': '1.0',
                                           'created': self.days_ago(5)})
        version_factory(addon=self.app, version='2.0',
                        file_kw=dict(status=mkt.STATUS_PENDING))
        self.app.reload()

    def _get_form(self, version, data=None):
        return forms.AppVersionForm(data, instance=version)

    def test_get_publish(self):
        form = self._get_form(self.app.latest_version)
        eq_(form.fields['publish_immediately'].initial, True)

        self.app.update(publish_type=mkt.PUBLISH_PRIVATE)
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
        eq_(self.app.publish_type, mkt.PUBLISH_IMMEDIATE)

        form = self._get_form(self.app.latest_version,
                              data={'publish_immediately': False})
        eq_(form.is_valid(), True)
        form.save()
        self.app.reload()
        eq_(self.app.publish_type, mkt.PUBLISH_PRIVATE)

    def test_post_publish_not_pending(self):
        # Using the current_version, which is public.
        form = self._get_form(self.app.current_version,
                              data={'publish_immediately': False})
        eq_(form.is_valid(), True)
        form.save()
        self.app.reload()
        eq_(self.app.publish_type, mkt.PUBLISH_IMMEDIATE)


class TestPublishForm(mkt.site.tests.TestCase):

    def setUp(self):
        self.app = app_factory(status=mkt.STATUS_PUBLIC)
        self.form = forms.PublishForm

    def test_initial(self):
        app = Webapp(status=mkt.STATUS_PUBLIC)
        eq_(self.form(None, addon=app).fields['publish_type'].initial,
            mkt.PUBLISH_IMMEDIATE)
        eq_(self.form(None, addon=app).fields['limited'].initial, False)

        app.status = mkt.STATUS_UNLISTED
        eq_(self.form(None, addon=app).fields['publish_type'].initial,
            mkt.PUBLISH_HIDDEN)
        eq_(self.form(None, addon=app).fields['limited'].initial, False)

        app.status = mkt.STATUS_APPROVED
        eq_(self.form(None, addon=app).fields['publish_type'].initial,
            mkt.PUBLISH_HIDDEN)
        eq_(self.form(None, addon=app).fields['limited'].initial, True)

    def test_go_public(self):
        self.app.update(status=mkt.STATUS_APPROVED)
        form = self.form({'publish_type': mkt.PUBLISH_IMMEDIATE,
                          'limited': False}, addon=self.app)
        assert form.is_valid()
        form.save()
        self.app.reload()
        eq_(self.app.status, mkt.STATUS_PUBLIC)

    @mock.patch('mkt.developers.forms.iarc_publish')
    def test_iarc_publish_is_called(self, iarc_publish_mock):
        self.create_switch('iarc-upgrade-v2')
        self.test_go_public()
        eq_(iarc_publish_mock.delay.call_count, 1)
        eq_(iarc_publish_mock.delay.call_args[0], (self.app.pk, ))

    def test_go_unlisted(self):
        self.app.update(status=mkt.STATUS_PUBLIC)
        form = self.form({'publish_type': mkt.PUBLISH_HIDDEN,
                          'limited': False}, addon=self.app)
        assert form.is_valid()
        form.save()
        self.app.reload()
        eq_(self.app.status, mkt.STATUS_UNLISTED)

    def test_go_private(self):
        self.app.update(status=mkt.STATUS_PUBLIC)
        form = self.form({'publish_type': mkt.PUBLISH_HIDDEN,
                          'limited': True}, addon=self.app)
        assert form.is_valid()
        form.save()
        self.app.reload()
        eq_(self.app.status, mkt.STATUS_APPROVED)

    def test_invalid(self):
        form = self.form({'publish_type': 999}, addon=self.app)
        assert not form.is_valid()


@mock.patch('mkt.webapps.models.Webapp.get_cached_manifest', mock.Mock)
class TestPublishFormPackaged(mkt.site.tests.TestCase):
    """
    Test that changing the app visibility doesn't affect the version statuses
    in weird ways.
    """

    def setUp(self):
        self.app = app_factory(status=mkt.STATUS_PUBLIC, is_packaged=True)
        self.ver1 = self.app.current_version
        self.ver1.update(created=self.days_ago(1))
        self.ver2 = version_factory(addon=self.app, version='2.0',
                                    file_kw=dict(status=mkt.STATUS_APPROVED))
        self.app.update(_latest_version=self.ver2)
        self.form = forms.PublishForm

    def test_initial(self):
        app = Webapp(status=mkt.STATUS_PUBLIC)
        eq_(self.form(None, addon=app).fields['publish_type'].initial,
            mkt.PUBLISH_IMMEDIATE)
        eq_(self.form(None, addon=app).fields['limited'].initial, False)

        app.status = mkt.STATUS_UNLISTED
        eq_(self.form(None, addon=app).fields['publish_type'].initial,
            mkt.PUBLISH_HIDDEN)
        eq_(self.form(None, addon=app).fields['limited'].initial, False)

        app.status = mkt.STATUS_APPROVED
        eq_(self.form(None, addon=app).fields['publish_type'].initial,
            mkt.PUBLISH_HIDDEN)
        eq_(self.form(None, addon=app).fields['limited'].initial, True)

    def test_go_public(self):
        self.app.update(status=mkt.STATUS_APPROVED)
        form = self.form({'publish_type': mkt.PUBLISH_IMMEDIATE,
                          'limited': False}, addon=self.app)
        assert form.is_valid()
        form.save()
        self.app.reload()
        eq_(self.app.status, mkt.STATUS_PUBLIC)
        eq_(self.app.current_version, self.ver1)
        eq_(self.app.latest_version, self.ver2)

    def test_go_private(self):
        self.app.update(status=mkt.STATUS_PUBLIC)
        form = self.form({'publish_type': mkt.PUBLISH_HIDDEN,
                          'limited': True}, addon=self.app)
        assert form.is_valid()
        form.save()
        self.app.reload()
        eq_(self.app.status, mkt.STATUS_APPROVED)
        eq_(self.app.current_version, self.ver1)
        eq_(self.app.latest_version, self.ver2)

    def test_go_unlisted(self):
        self.app.update(status=mkt.STATUS_PUBLIC)
        form = self.form({'publish_type': mkt.PUBLISH_HIDDEN,
                          'limited': False}, addon=self.app)
        assert form.is_valid()
        form.save()
        self.app.reload()
        eq_(self.app.status, mkt.STATUS_UNLISTED)
        eq_(self.app.current_version, self.ver1)
        eq_(self.app.latest_version, self.ver2)

    def test_invalid(self):
        form = self.form({'publish_type': 999}, addon=self.app)
        assert not form.is_valid()


class TestAdminSettingsForm(TestAdmin):

    def setUp(self):
        super(TestAdminSettingsForm, self).setUp()
        self.data = {'position': 1}
        self.user = UserProfile.objects.get(email='admin@mozilla.com')
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


class TestIARCGetAppInfoForm(mkt.site.tests.WebappTestCase):

    def _get_form(self, app=None, **kwargs):
        data = {
            'submission_id': 1,
            'security_code': 'a'
        }
        data.update(kwargs)
        return forms.IARCGetAppInfoForm(data=data, app=app or self.app)

    def test_good(self):
        with self.assertRaises(IARCInfo.DoesNotExist):
            self.app.iarc_info

        form = self._get_form()
        assert form.is_valid(), form.errors
        form.save()

        iarc_info = IARCInfo.objects.get(addon=self.app)
        eq_(iarc_info.submission_id, 1)
        eq_(iarc_info.security_code, 'a')

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

        some_app = app_factory()
        form = self._get_form(app=some_app)
        ok_(not form.is_valid())

        form = self._get_form(app=some_app, submission_id=2)
        ok_(form.is_valid())

    @mock.patch.object(settings, 'IARC_ALLOW_CERT_REUSE', True)
    def test_iarc_already_used_dev(self):
        self.app.set_iarc_info(1, 'a')
        form = self._get_form()
        ok_(form.is_valid())

    def test_changing_cert(self):
        self.app.set_iarc_info(1, 'a')
        form = self._get_form(submission_id=2, security_code='b')
        ok_(form.is_valid(), form.errors)
        form.save()

        iarc_info = self.app.iarc_info.reload()
        eq_(iarc_info.submission_id, 2)
        eq_(iarc_info.security_code, 'b')

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

    def test_bad_submission_id(self):
        form = self._get_form(submission_id='subwayeatfresh-133')
        assert not form.is_valid()

    def test_incomplete(self):
        form = self._get_form(submission_id=None)
        assert not form.is_valid(), 'Form was expected to be invalid.'

    @mock.patch('lib.iarc.utils.IARC_XML_Parser.parse_string')
    def test_rating_not_found(self, _mock):
        _mock.return_value = {'rows': [
            {'ActionStatus': 'No records found. Please try another criteria.'}
        ]}
        form = self._get_form()
        assert form.is_valid(), form.errors
        with self.assertRaises(django_forms.ValidationError):
            form.save()


class TestIARCV2ExistingCertificateForm(mkt.site.tests.WebappTestCase):
    def setUp(self):
        self.app = app_factory(status=mkt.STATUS_PUBLIC, is_packaged=True)
        super(TestIARCV2ExistingCertificateForm, self).setUp()

    def test_cert_id_required(self):
        data = {}
        form = forms.IARCV2ExistingCertificateForm(data=data, app=self.app)
        eq_(form.is_valid(), False)
        eq_(form.errors['cert_id'], ['This field is required.'])

    def test_cert_id_value_0_invalid_in_prod(self):
        data = {
            'cert_id': '0'
        }
        form = forms.IARCV2ExistingCertificateForm(data=data, app=self.app)
        eq_(form.is_valid(), False)
        eq_(form.errors['cert_id'], ['badly formed hexadecimal UUID string'])

    @override_settings(DEBUG=True)
    def test_cert_id_value_0_valid_in_debug_mode(self):
        data = {
            'cert_id': '0'
        }
        form = forms.IARCV2ExistingCertificateForm(data=data, app=self.app)
        eq_(form.is_valid(), True)
        eq_(form.errors, {})
        eq_(form.cleaned_data['cert_id'], None)  # Will be handled by save().
        return form

    def test_cert_id_valid_uuid_with_separators(self):
        cert = uuid.uuid4()
        data = {
            'cert_id': unicode(cert)
        }
        form = forms.IARCV2ExistingCertificateForm(data=data, app=self.app)
        eq_(form.is_valid(), True)
        eq_(form.errors, {})
        eq_(form.cleaned_data['cert_id'], unicode(cert))
        return form

    def test_cert_id_valid_uuid_no_separators(self):
        cert = uuid.uuid4()
        data = {
            'cert_id': cert.get_hex()
        }
        form = forms.IARCV2ExistingCertificateForm(data=data, app=self.app)
        eq_(form.is_valid(), True)
        eq_(form.errors, {})
        eq_(form.cleaned_data['cert_id'], unicode(cert))

    def test_cert_id_valid_uuid_with_separators_already_used(self):
        cert = uuid.uuid4()
        data = {
            'cert_id': cert.get_hex()
        }
        # If another app is using this cert, the form should be invalid.
        iarc_cert = IARCCert.objects.create(app=app_factory(), cert_id=cert)
        form = forms.IARCV2ExistingCertificateForm(data=data, app=self.app)
        eq_(form.is_valid(), False)
        eq_(form.errors['cert_id'],
            ['This IARC certificate is already being used for another '
             'app. Please create a new IARC Ratings Certificate.'])

        # If the cert is used by the same app, then it should be valid:
        iarc_cert.update(app=self.app)
        form = forms.IARCV2ExistingCertificateForm(data=data, app=self.app)
        eq_(form.is_valid(), True)
        eq_(form.cleaned_data['cert_id'], unicode(cert))

    def test_cert_id_valid_uuid_no_separators_already_used(self):
        cert = uuid.uuid4()
        data = {
            'cert_id': cert.get_hex()
        }
        # If another app is using this cert, the form should be invalid.
        iarc_cert = IARCCert.objects.create(app=app_factory(), cert_id=cert)
        form = forms.IARCV2ExistingCertificateForm(data=data, app=self.app)
        eq_(form.is_valid(), False)
        eq_(form.errors['cert_id'],
            ['This IARC certificate is already being used for another '
             'app. Please create a new IARC Ratings Certificate.'])

        # If the cert is used by the same app, then it should be valid:
        iarc_cert.update(app=self.app)
        form = forms.IARCV2ExistingCertificateForm(data=data, app=self.app)
        eq_(form.is_valid(), True)
        eq_(form.cleaned_data['cert_id'], unicode(cert))

    def test_cert_id_invalid(self):
        data = {
            'cert_id': 'garbage'
        }
        form = forms.IARCV2ExistingCertificateForm(data=data, app=self.app)
        eq_(form.is_valid(), False)
        eq_(form.errors['cert_id'], ['badly formed hexadecimal UUID string'])
        return form

    def test_save_invalid(self):
        form = self.test_cert_id_invalid()
        with self.assertRaises(django_forms.ValidationError):
            form.save()

    @override_settings(DEBUG=True)
    def test_save_debug(self):
        form = self.test_cert_id_value_0_valid_in_debug_mode()
        form.save()
        descriptors = self.app.rating_descriptors
        eq_(descriptors.to_keys(), [])

        interactives = self.app.rating_interactives
        eq_(interactives.to_keys(), [])

        content_rating = self.app.content_ratings.get()
        eq_(content_rating.ratings_body, ratingsbodies.ESRB.id)
        eq_(content_rating.rating, ratingsbodies.ESRB_E.id)

    @mock.patch('mkt.developers.forms.search_and_attach_cert')
    def test_save(self, search_and_attach_cert_mock):
        form = self.test_cert_id_valid_uuid_with_separators()
        form.save()
        eq_(search_and_attach_cert_mock.call_count, 1)
        eq_(search_and_attach_cert_mock.call_args[0],
            (self.app, form.cleaned_data['cert_id']))

    @mock.patch('mkt.developers.forms.search_and_attach_cert')
    def test_save_iarc_error(self, search_and_attach_cert_mock):
        search_and_attach_cert_mock.side_effect = IARCException
        form = self.test_cert_id_valid_uuid_with_separators()
        with self.assertRaises(django_forms.ValidationError):
            form.save()
        ok_(form.errors['cert_id'][0].startswith(
            'This Certificate ID is not recognized by IARC'))


class TestAPIForm(mkt.site.tests.WebappTestCase):

    def setUp(self):
        super(TestAPIForm, self).setUp()
        self.form = forms.APIConsumerForm

    def test_non_url(self):
        form = self.form({
            'app_name': 'test',
            'redirect_uri': 'mailto:cvan@example.com',
            'oauth_leg': 'website'
        })
        assert not form.is_valid()
        eq_(form.errors['redirect_uri'], ['Enter a valid URL.'])

    def test_non_app_name(self):
        form = self.form({
            'redirect_uri': 'mailto:cvan@example.com',
            'oauth_leg': 'website'
        })
        assert not form.is_valid()
        eq_(form.errors['app_name'], ['This field is required.'])

    def test_command(self):
        form = self.form({'oauth_leg': 'command'})
        assert form.is_valid()

    def test_website(self):
        form = self.form({
            'app_name': 'test',
            'redirect_uri': 'https://f.com',
            'oauth_leg': 'website'
        })
        assert form.is_valid()
