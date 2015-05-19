# -*- coding: utf-8 -*-
import json
import os
import tempfile

from django.conf import settings
from django.core.files.storage import default_storage as storage
from django.core.urlresolvers import reverse
from django.forms.fields import Field
from django.utils.encoding import smart_unicode

import mock
from jinja2.utils import escape
from nose import SkipTest
from nose.tools import eq_, ok_
from PIL import Image
from pyquery import PyQuery as pq

import mkt
import mkt.site.tests
from lib.video.tests import files as video_files
from mkt.access.models import Group, GroupUser
from mkt.comm.models import CommunicationNote
from mkt.constants import comm, regions
from mkt.developers.models import ActivityLog
from mkt.reviewers.models import RereviewQueue
from mkt.site.fixtures import fixture
from mkt.site.helpers import absolutify
from mkt.site.tests import formset, initial
from mkt.site.tests.test_utils_ import get_image_path
from mkt.site.utils import app_factory
from mkt.translations.models import Translation
from mkt.users.models import UserProfile
from mkt.versions.models import Version
from mkt.webapps.models import AddonExcludedRegion as AER
from mkt.webapps.models import AddonDeviceType, AddonUser, Webapp


response_mock = mock.Mock()
response_mock.read.return_value = '''
    {
        "name": "Something Ballin!",
        "description": "Goin' hard in the paint.",
        "launch_path": "/ballin/4.eva",
        "developer": {
            "name": "Pro Balliner",
            "url": "http://www.ballin4eva.xxx"
        },
        "icons": {
            "128": "/ballin/icon.png"
        },
        "installs_allowed_from": [ "https://marketplace.firefox.com" ]
    }
'''
response_mock.headers = {'Content-Type':
                         'application/x-web-app-manifest+json'}


def get_section_url(addon, section, edit=False):
    args = [addon.app_slug, section]
    if edit:
        args.append('edit')
    return reverse('mkt.developers.apps.section', args=args)


class TestEdit(mkt.site.tests.TestCase):
    fixtures = fixture('group_admin', 'user_999', 'user_admin',
                       'user_admin_group', 'webapp_337141')

    def setUp(self):
        self.webapp = self.get_webapp()
        self.url = self.webapp.get_dev_url()
        self.user = UserProfile.objects.get(email='steamcube@mozilla.com')
        self.login(self.user.email)

    def get_webapp(self):
        return Webapp.objects.no_cache().get(id=337141)

    def get_url(self, section, edit=False):
        return get_section_url(self.webapp, section, edit)

    def get_dict(self, **kw):
        fs = formset(self.cat_initial, initial_count=1)
        result = {'name': 'new name', 'slug': 'test_slug',
                  'description': 'new description'}
        result.update(**kw)
        result.update(fs)
        return result

    def compare(self, data, instance=None):
        """Compare an app against a `dict` of expected values."""
        mapping = {
            'regions': 'get_region_ids'
        }

        if instance is None:
            instance = self.get_webapp()
        for k, v in data.iteritems():
            k = mapping.get(k, k)
            val = getattr(instance, k, '')
            if callable(val):
                val = val()
            if val is None:
                val = ''

            eq_(unicode(val), unicode(v))

    def compare_features(self, data, version=None):
        """
        Compare an app's set of required features against a `dict` of expected
        values.
        """
        if not version:
            version = self.get_webapp().current_version
        features = version.features
        for k, v in data.iteritems():
            val = getattr(features, k)
            if callable(val):
                val = val()
            eq_(unicode(val), unicode(v))

    def check_form_url(self, section):
        # Check form destinations and "Edit" button.
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        doc = pq(r.content)
        eq_(doc('form').attr('action'), self.edit_url)
        eq_(doc('h2 .button').attr('data-editurl'), self.edit_url)

        # Check "Cancel" button.
        r = self.client.get(self.edit_url)
        eq_(pq(r.content)('form .addon-edit-cancel').attr('href'), self.url)


class TestEditListingWebapp(TestEdit):
    fixtures = fixture('webapp_337141')

    def test_redirect(self):
        r = self.client.get(self.url.replace('edit', ''))
        self.assert3xx(r, self.url)

    def test_nav_links(self):
        r = self.client.get(self.url)
        doc = pq(r.content)('.edit-addon-nav')
        eq_(doc.length, 2)
        eq_(doc('.view-stats').length, 0)

    def test_edit_with_no_current_version(self):
        # Disable file for latest version, and then update app.current_version.
        app = self.get_webapp()
        app.versions.latest().all_files[0].update(status=mkt.STATUS_DISABLED)
        app.update_version()

        # Now try to display edit page.
        r = self.client.get(self.url)
        eq_(r.status_code, 200)

    def test_edit_global_xss_name(self):
        self.webapp.name = u'My app é <script>alert(5)</script>'
        self.webapp.save()
        content = smart_unicode(self.client.get(self.url).content)
        ok_(not unicode(self.webapp.name) in content)
        ok_(unicode(escape(self.webapp.name)) in content)


@mock.patch.object(settings, 'TASK_USER_ID', 999)
class TestEditBasic(TestEdit):
    fixtures = TestEdit.fixtures

    def setUp(self):
        super(TestEditBasic, self).setUp()
        self.cat = 'games'
        self.dtype = mkt.DEVICE_TYPES.keys()[0]
        self.webapp.update(categories=['games'])
        AddonDeviceType.objects.create(addon=self.webapp,
                                       device_type=self.dtype)
        self.url = self.get_url('basic')
        self.edit_url = self.get_url('basic', edit=True)

    def get_webapp(self):
        return Webapp.objects.get(id=337141)

    def get_dict(self, **kw):
        result = {'device_types': self.dtype, 'slug': 'NeW_SluG',
                  'description': 'New description with <em>html</em>!',
                  'manifest_url': self.webapp.manifest_url,
                  'categories': [self.cat]}
        result.update(**kw)
        return result

    def test_form_url(self):
        self.check_form_url('basic')

    def test_appslug_visible(self):
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        eq_(pq(r.content)('#slug_edit').remove('a, em').text(),
            absolutify(u'/\u2026/%s' % self.webapp.app_slug))

    def test_edit_slug_success(self):
        data = self.get_dict()
        r = self.client.post(self.edit_url, data)
        self.assertNoFormErrors(r)
        eq_(r.status_code, 200)
        webapp = self.get_webapp()
        eq_(webapp.app_slug, data['slug'].lower())

    def test_edit_slug_max_length(self):
        r = self.client.post(self.edit_url, self.get_dict(slug='x' * 31))
        self.assertFormError(
            r, 'form', 'slug',
            'Ensure this value has at most 30 characters (it has 31).')

    def test_edit_slug_dupe(self):
        Webapp.objects.create(app_slug='dupe')
        r = self.client.post(self.edit_url, self.get_dict(slug='dupe'))
        self.assertFormError(
            r, 'form', 'slug',
            'This slug is already in use. Please choose another.')
        webapp = self.get_webapp()
        # Nothing changed.
        eq_(webapp.app_slug, self.webapp.app_slug)

    def test_edit_xss_description(self):
        self.webapp.description = ("This\n<b>IS</b>"
                                   "<script>alert('awesome')</script>")
        self.webapp.save()
        r = self.client.get(self.url)
        eq_(pq(r.content)('#addon-description span[lang]').html(),
            "This<br/><b>IS</b>&lt;script&gt;alert('awesome')"
            '&lt;/script&gt;')

    def test_edit_xss_name(self):
        self.webapp.name = u'My app é <script>alert(5)</script>'
        self.webapp.save()
        content = smart_unicode(self.client.get(self.url).content)
        ok_(not unicode(self.webapp.name) in content)
        ok_(unicode(escape(self.webapp.name)) in content)

    def test_view_edit_manifest_url_empty(self):
        # Empty manifest should throw an error.
        r = self.client.post(self.edit_url, self.get_dict(manifest_url=''))
        form = r.context['form']
        assert 'manifest_url' in form.errors
        assert 'This field is required' in form.errors['manifest_url'][0]

    @mock.patch('mkt.developers.forms.update_manifests')
    def test_view_edit_manifest_url(self, fetch):
        assert not self.webapp.in_rereview_queue(), (
            'App should not be in re-review queue')

        # Should be able to see manifest URL listed.
        r = self.client.get(self.url)
        eq_(pq(r.content)('#manifest-url a').attr('href'),
            self.webapp.manifest_url)

        # Devs/admins can edit the manifest URL and should see a text field.
        r = self.client.get(self.edit_url)
        row = pq(r.content)('#manifest-url')
        eq_(row.find('input[name=manifest_url]').length, 1)
        eq_(row.find('input[name=manifest_url][readonly]').length, 0)

        # POST with the new manifest URL.
        url = 'https://ballin.com/ballin4eva.webapp'
        r = self.client.post(self.edit_url, self.get_dict(manifest_url=url))
        self.assertNoFormErrors(r)

        self.webapp = self.get_webapp()
        eq_(self.webapp.manifest_url, url)
        eq_(self.webapp.app_domain, 'https://ballin.com')
        eq_(self.webapp.current_version.version, '1.0')
        eq_(self.webapp.versions.count(), 1)

        assert self.webapp.in_rereview_queue(), (
            'App should be in re-review queue')

        # Ensure that we're refreshing the manifest.
        fetch.delay.assert_called_once_with([self.webapp.pk])

    @mock.patch('mkt.developers.forms.update_manifests')
    def test_view_manifest_changed_dupe_app_domain(self, fetch):
        self.create_switch('webapps-unique-by-domain')
        app_factory(name='Super Duper',
                    app_domain='https://ballin.com')
        self.login('admin')

        # POST with new manifest URL.
        url = 'https://ballin.com/ballin4eva.webapp'
        r = self.client.post(self.edit_url, self.get_dict(manifest_url=url))
        form = r.context['form']
        assert 'manifest_url' in form.errors
        assert 'one app per domain' in form.errors['manifest_url'][0]

        eq_(self.get_webapp().manifest_url, self.webapp.manifest_url,
            'Manifest URL should not have been changed!')

        assert not fetch.delay.called, (
            'Manifest should not have been refreshed!')

    @mock.patch('mkt.developers.forms.update_manifests')
    def test_view_manifest_changed_same_domain_diff_path(self, fetch):
        self.create_switch('webapps-unique-by-domain')
        self.login('admin')

        # POST with new manifest URL for same domain but w/ different path.
        data = self.get_dict(manifest_url=self.webapp.manifest_url + 'xxx')
        r = self.client.post(self.edit_url, data)
        self.assertNoFormErrors(r)

        eq_(self.get_webapp().manifest_url, self.webapp.manifest_url + 'xxx',
            'Manifest URL should have changed!')

        assert not self.webapp.in_rereview_queue(), (
            'App should be in re-review queue because an admin changed it')

        # Ensure that we're refreshing the manifest.
        fetch.delay.assert_called_once_with([self.webapp.pk])

    def test_view_manifest_url_changed(self):
        new_url = 'http://omg.org/yes'
        self.webapp.manifest_url = new_url
        self.webapp.save()

        # If we change the `manifest_url` manually, the URL here should change.
        r = self.client.get(self.url)
        eq_(pq(r.content)('#manifest-url a').attr('href'), new_url)

    def test_categories_listed(self):
        r = self.client.get(self.url)
        eq_(pq(r.content)('#addon-categories-edit').text(), unicode('Games'))

        r = self.client.post(self.url)
        eq_(pq(r.content)('#addon-categories-edit').text(), unicode('Games'))

    def test_edit_categories_add(self):
        new = 'books'
        cats = [self.cat, new]
        self.client.post(self.edit_url, self.get_dict(categories=cats))
        eq_(sorted(self.get_webapp().categories), sorted(cats))

    def test_edit_categories_addandremove(self):
        new = 'books'
        cats = [new]
        self.client.post(self.edit_url, self.get_dict(categories=cats))
        eq_(sorted(self.get_webapp().categories), sorted(cats))

    @mock.patch('mkt.webapps.models.Webapp.save')
    def test_edit_categories_required(self, save):
        r = self.client.post(self.edit_url, self.get_dict(categories=[]))
        eq_(r.context['cat_form'].errors['categories'][0],
            unicode(Field.default_error_messages['required']))
        assert not save.called

    def test_edit_categories_xss(self):
        new = '<script>alert("xss");</script>'
        cats = [self.cat, new]
        r = self.client.post(self.edit_url, self.get_dict(categories=cats))

        assert '<script>alert' not in r.content
        assert '&lt;script&gt;alert' in r.content

    def test_edit_categories_nonexistent(self):
        r = self.client.post(self.edit_url, self.get_dict(categories=[100]))
        eq_(r.context['cat_form'].errors['categories'],
            ['Select a valid choice. 100 is not one of the available '
             'choices.'])

    def test_edit_categories_max(self):
        cats = [self.cat, 'books', 'social']
        r = self.client.post(self.edit_url, self.get_dict(categories=cats))
        eq_(r.context['cat_form'].errors['categories'],
            ['You can have only 2 categories.'])

    def test_edit_check_description(self):
        # Make sure bug 629779 doesn't return.
        r = self.client.post(self.edit_url, self.get_dict())
        eq_(r.status_code, 200)
        eq_(self.get_webapp().description, self.get_dict()['description'])

    def test_edit_slug_valid(self):
        old_edit = self.edit_url
        data = self.get_dict(slug='valid')
        r = self.client.post(self.edit_url, data)
        doc = pq(r.content)
        assert doc('form').attr('action') != old_edit

    def test_edit_as_developer(self):
        self.login('regular@mozilla.com')
        data = self.get_dict()
        r = self.client.post(self.edit_url, data)
        # Make sure we get errors when they are just regular users.
        eq_(r.status_code, 403)

        AddonUser.objects.create(addon=self.webapp, user_id=999,
                                 role=mkt.AUTHOR_ROLE_DEV)
        r = self.client.post(self.edit_url, data)
        eq_(r.status_code, 200)
        webapp = self.get_webapp()

        eq_(unicode(webapp.app_slug), data['slug'].lower())
        eq_(unicode(webapp.description), data['description'])

    def test_l10n(self):
        self.webapp.update(default_locale='en-US')
        url = self.webapp.get_dev_url('edit')
        r = self.client.get(url)
        eq_(pq(r.content)('#l10n-menu').attr('data-default'), 'en-us',
            'l10n menu not visible for %s' % url)

    def test_l10n_not_us(self):
        self.webapp.update(default_locale='fr')
        url = self.webapp.get_dev_url('edit')
        r = self.client.get(url)
        eq_(pq(r.content)('#l10n-menu').attr('data-default'), 'fr',
            'l10n menu not visible for %s' % url)

    def test_edit_l10n(self):
        data = {
            'slug': self.webapp.app_slug,
            'manifest_url': self.webapp.manifest_url,
            'categories': [self.cat],
            'description_en-us': u'Nêw english description',
            'description_fr': u'Nëw french description',
            'releasenotes_en-us': u'Nëw english release notes',
            'releasenotes_fr': u'Nêw french release notes'
        }
        res = self.client.post(self.edit_url, data)
        eq_(res.status_code, 200)
        self.webapp = self.get_webapp()
        version = self.webapp.current_version.reload()
        desc_id = self.webapp.description_id
        notes_id = version.releasenotes_id
        eq_(self.webapp.description, data['description_en-us'])
        eq_(version.releasenotes, data['releasenotes_en-us'])
        eq_(unicode(Translation.objects.get(id=desc_id, locale='fr')),
            data['description_fr'])
        eq_(unicode(Translation.objects.get(id=desc_id, locale='en-us')),
            data['description_en-us'])
        eq_(unicode(Translation.objects.get(id=notes_id, locale='fr')),
            data['releasenotes_fr'])
        eq_(unicode(Translation.objects.get(id=notes_id, locale='en-us')),
            data['releasenotes_en-us'])

    @mock.patch('mkt.developers.views._update_manifest')
    def test_refresh(self, fetch):
        self.login('steamcube@mozilla.com')
        url = reverse('mkt.developers.apps.refresh_manifest',
                      args=[self.webapp.app_slug])
        r = self.client.post(url)
        eq_(r.status_code, 204)
        fetch.assert_called_once_with(self.webapp.pk, True, {})

    @mock.patch('mkt.developers.views._update_manifest')
    def test_refresh_dev_only(self, fetch):
        self.login('regular@mozilla.com')
        url = reverse('mkt.developers.apps.refresh_manifest',
                      args=[self.webapp.app_slug])
        r = self.client.post(url)
        eq_(r.status_code, 403)
        eq_(fetch.called, 0)

    def test_view_developer_name(self):
        r = self.client.get(self.url)
        developer_name = self.webapp.current_version.developer_name
        content = smart_unicode(r.content)
        eq_(pq(content)('#developer-name td').html().strip(), developer_name)

    def test_view_developer_name_xss(self):
        version = self.webapp.current_version
        version._developer_name = '<script>alert("xss-devname")</script>'
        version.save()

        r = self.client.get(self.url)

        assert '<script>alert' not in r.content
        assert '&lt;script&gt;alert' in r.content

    def test_edit_packaged(self):
        self.get_webapp().update(is_packaged=True)
        data = self.get_dict()
        data.pop('manifest_url')
        r = self.client.post(self.edit_url, data)
        eq_(r.status_code, 200)
        eq_(r.context['editable'], False)
        eq_(self.get_webapp().description, self.get_dict()['description'])

    def test_edit_basic_not_public(self):
        # Disable file for latest version, and then update app.current_version.
        app = self.get_webapp()
        app.versions.latest().all_files[0].update(status=mkt.STATUS_DISABLED)
        app.update_version()

        # Now try to display edit page.
        r = self.client.get(self.url)
        eq_(r.status_code, 200)

    def test_view_release_notes(self):
        version = self.webapp.current_version
        version.releasenotes = u'Chëese !'
        version.save()
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        content = smart_unicode(res.content)
        eq_(pq(content)('#releasenotes td span[lang]').html().strip(),
            version.releasenotes)

        self.webapp.update(is_packaged=True)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        content = smart_unicode(res.content)
        eq_(pq(content)('#releasenotes').length, 0)

    def test_edit_release_notes(self):
        self.webapp.previews.create()
        self.webapp.support_email = 'test@example.com'
        self.webapp.save()
        data = self.get_dict(releasenotes=u'I can hâz release notes')
        res = self.client.post(self.edit_url, data)
        releasenotes = self.webapp.reload().latest_version.releasenotes
        eq_(res.status_code, 200)
        eq_(releasenotes, data['releasenotes'])
        # Make sure publish_type wasn't reset by accident.
        eq_(self.webapp.reload().publish_type, mkt.PUBLISH_IMMEDIATE)

    def test_edit_release_notes_pending(self):
        # Like test_edit_release_notes, but with a pending app.
        file_ = self.webapp.current_version.all_files[0]
        file_.update(status=mkt.STATUS_PENDING)
        self.webapp.update(status=mkt.STATUS_PENDING)
        self.test_edit_release_notes()
        eq_(self.webapp.reload().status, mkt.STATUS_PENDING)

    def test_edit_release_notes_packaged(self):
        # You are not supposed to edit release notes from the basic edit
        # page if you app is packaged. Instead this is done from the version
        # edit page.
        self.webapp.update(is_packaged=True)
        data = self.get_dict(releasenotes=u'I can not hâz release notes')
        res = self.client.post(self.edit_url, data)
        releasenotes = self.webapp.current_version.reload().releasenotes
        eq_(res.status_code, 200)
        eq_(releasenotes, None)

    def test_view_releasenotes_xss(self):
        version = self.webapp.current_version
        version.releasenotes = '<script>alert("xss-devname")</script>'
        version.save()
        r = self.client.get(self.url)
        assert '<script>alert' not in r.content
        assert '&lt;script&gt;alert' in r.content


class TestEditCountryLanguage(TestEdit):
    # Note: those tests used to use pyquery, but it was unreliable because of
    # unicode-related issues - travis expected a wrong result. To make sure
    # they are not wrong, the assertion is done manually without pyquery.

    def get_webapp(self):
        return Webapp.objects.get(id=337141)

    def test_languages(self):
        self.get_webapp().current_version.update(supported_locales='de,es')
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        ok_(u'English (US) (default), Deutsch, Español'
            in smart_unicode(res.content))

    def test_countries(self):
        self.get_webapp().current_version.update(supported_locales='de,es')
        res = self.client.get(self.url)
        eq_(res.status_code, 200)

        # Reproduce the (weird) ordering we expect.
        listed_countries = self.get_webapp().get_region_ids(restofworld=True)
        countries = [unicode(regions.REGIONS_CHOICES_ID_DICT.get(region).name)
                     for region in listed_countries]
        # Escape like it should be.
        ok_(escape(u', '.join(countries)) in smart_unicode(res.content))


class TestEditMedia(TestEdit):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        super(TestEditMedia, self).setUp()
        self.url = self.get_url('media')
        self.edit_url = self.get_url('media', True)
        self.icon_upload = self.webapp.get_dev_url('upload_icon')
        self.preview_upload = self.webapp.get_dev_url('upload_preview')
        patches = {
            'ADDON_ICONS_PATH': tempfile.mkdtemp(),
            'PREVIEW_THUMBNAIL_PATH': tempfile.mkstemp()[1] + '%s/%d.png',
        }
        for k, v in patches.iteritems():
            patcher = mock.patch.object(settings, k, v)
            patcher.start()
            self.addCleanup(patcher.stop)

    def formset_new_form(self, *args, **kw):
        ctx = self.client.get(self.edit_url).context

        blank = initial(ctx['preview_form'].forms[-1])
        blank.update(**kw)
        return blank

    def formset_media(self, prev_blank=None, *args, **kw):
        prev_blank = prev_blank or {}
        kw.setdefault('initial_count', 0)
        kw.setdefault('prefix', 'files')

        # Preview formset.
        fs = formset(*list(args) + [self.formset_new_form(**prev_blank)], **kw)

        return dict((k, '' if v is None else v) for k, v in fs.items())

    def new_preview_hash(self):
        # At least one screenshot is required.
        src_image = open(get_image_path('preview.jpg'), 'rb')
        r = self.client.post(self.preview_upload,
                             dict(upload_image=src_image))
        return {'upload_hash': json.loads(r.content)['upload_hash']}

    def test_form_url(self):
        self.check_form_url('media')

    def test_edit_defaulticon(self):
        data = dict(icon_type='')
        data_formset = self.formset_media(prev_blank=self.new_preview_hash(),
                                          **data)

        r = self.client.post(self.edit_url, data_formset)
        self.assertNoFormErrors(r)
        webapp = self.get_webapp()

        assert webapp.get_icon_url(128).endswith('default-128.png')
        assert webapp.get_icon_url(64).endswith('default-64.png')

        for k in data:
            eq_(unicode(getattr(webapp, k)), data[k])

    def test_edit_uploadedicon(self):
        img = get_image_path('mozilla-sq.png')
        src_image = open(img, 'rb')

        response = self.client.post(self.icon_upload,
                                    dict(upload_image=src_image))
        response_json = json.loads(response.content)
        webapp = self.get_webapp()

        # Now, save the form so it gets moved properly.
        data = dict(icon_type='image/png',
                    icon_upload_hash=response_json['upload_hash'])
        data_formset = self.formset_media(prev_blank=self.new_preview_hash(),
                                          **data)

        r = self.client.post(self.edit_url, data_formset)
        self.assertNoFormErrors(r)
        webapp = self.get_webapp()

        # Unfortunate hardcoding of URL.
        url = webapp.get_icon_url(64)
        assert ('addon_icons/%s/%s' % (webapp.id / 1000, webapp.id)) in url, (
            'Unexpected path: %r' % url)

        eq_(data['icon_type'], 'image/png')

        # Check that it was actually uploaded.
        dirname = os.path.join(settings.ADDON_ICONS_PATH,
                               '%s' % (webapp.id / 1000))
        dest = os.path.join(dirname, '%s-32.png' % webapp.id)

        eq_(storage.exists(dest), True)

        eq_(Image.open(storage.open(dest)).size, (32, 32))

    def test_edit_icon_log(self):
        self.test_edit_uploadedicon()
        log = ActivityLog.objects.all()
        eq_(log.count(), 1)
        eq_(log[0].action, mkt.LOG.CHANGE_ICON.id)

    def test_edit_uploadedicon_noresize(self):
        img = '%s/img/mkt/logos/128.png' % settings.MEDIA_ROOT
        src_image = open(img, 'rb')

        data = dict(upload_image=src_image)

        response = self.client.post(self.icon_upload, data)
        response_json = json.loads(response.content)
        webapp = self.get_webapp()

        # Now, save the form so it gets moved properly.
        data = dict(icon_type='image/png',
                    icon_upload_hash=response_json['upload_hash'])
        data_formset = self.formset_media(prev_blank=self.new_preview_hash(),
                                          **data)

        r = self.client.post(self.edit_url, data_formset)
        self.assertNoFormErrors(r)
        webapp = self.get_webapp()

        # Unfortunate hardcoding of URL.
        addon_url = webapp.get_icon_url(64).split('?')[0]
        end = 'addon_icons/%s/%s-64.png' % (webapp.id / 1000, webapp.id)
        assert addon_url.endswith(end), 'Unexpected path: %r' % addon_url

        eq_(data['icon_type'], 'image/png')

        # Check that it was actually uploaded.
        dirname = os.path.join(settings.ADDON_ICONS_PATH,
                               '%s' % (webapp.id / 1000))
        dest = os.path.join(dirname, '%s-64.png' % webapp.id)

        assert storage.exists(dest), dest

        eq_(Image.open(storage.open(dest)).size, (64, 64))

    def test_media_types(self):
        res = self.client.get(self.get_url('media', edit=True))
        doc = pq(res.content)
        eq_(doc('#id_icon_upload').attr('data-allowed-types'),
            'image/jpeg|image/png')
        eq_(doc('.screenshot_upload').attr('data-allowed-types'),
            'image/jpeg|image/png|video/webm')

    def check_image_type(self, url, msg):
        img = '%s/js/devreg/devhub.js' % settings.MEDIA_ROOT
        self.check_image_type_path(img, url, msg)

    def check_image_type_path(self, img, url, msg):
        src_image = open(img, 'rb')

        res = self.client.post(url, {'upload_image': src_image})
        response_json = json.loads(res.content)
        assert any(e == msg for e in response_json['errors']), (
            response_json['errors'])

    # The check_image_type method uploads js, so let's try sending that
    # to ffmpeg to see what it thinks.
    @mock.patch.object(mkt, 'VIDEO_TYPES', ['application/javascript'])
    def test_edit_video_wrong_type(self):
        raise SkipTest
        self.check_image_type(self.preview_upload, 'Videos must be in WebM.')

    def test_edit_icon_wrong_type(self):
        self.check_image_type(self.icon_upload,
                              'Icons must be either PNG or JPG.')

    def test_edit_screenshot_wrong_type(self):
        self.check_image_type(self.preview_upload,
                              'Images must be either PNG or JPG.')

    def setup_image_status(self):
        self.icon_dest = os.path.join(self.webapp.get_icon_dir(),
                                      '%s-64.png' % self.webapp.id)
        os.makedirs(os.path.dirname(self.icon_dest))
        open(self.icon_dest, 'w')

        self.preview = self.webapp.previews.create()
        self.preview.save()
        os.makedirs(os.path.dirname(self.preview.thumbnail_path))
        open(self.preview.thumbnail_path, 'w')

        self.url = self.webapp.get_dev_url('ajax.image.status')

    def test_icon_square(self):
        img = get_image_path('mozilla.png')
        self.check_image_type_path(img, self.icon_upload,
                                   'Icons must be square.')

    def test_icon_status_no_choice(self):
        self.webapp.update(icon_type='')
        url = self.webapp.get_dev_url('ajax.image.status')
        result = json.loads(self.client.get(url).content)
        assert result['icons']

    def test_icon_status_works(self):
        self.setup_image_status()
        result = json.loads(self.client.get(self.url).content)
        assert result['icons']

    def test_icon_status_fails(self):
        self.setup_image_status()
        os.remove(self.icon_dest)
        result = json.loads(self.client.get(self.url).content)
        assert not result['icons']

    def test_preview_status_works(self):
        self.setup_image_status()
        result = json.loads(self.client.get(self.url).content)
        assert result['previews']

        # No previews means that all the images are done.
        self.webapp.previews.all().delete()
        result = json.loads(self.client.get(self.url).content)
        assert result['previews']

    def test_preview_status_fails(self):
        self.setup_image_status()
        os.remove(self.preview.thumbnail_path)
        result = json.loads(self.client.get(self.url).content)
        assert not result['previews']

    def test_image_status_default(self):
        self.setup_image_status()
        os.remove(self.icon_dest)
        self.webapp.update(icon_type='icon/photos')
        result = json.loads(self.client.get(self.url).content)
        assert result['icons']

    def test_icon_size_req(self):
        filehandle = open(get_image_path('mkt_icon_72.png'), 'rb')

        res = self.client.post(self.icon_upload, {'upload_image': filehandle})
        response_json = json.loads(res.content)
        assert any(e == 'Icons must be at least 128px by 128px.' for e in
                   response_json['errors'])

    def check_image_animated(self, url, msg):
        filehandle = open(get_image_path('animated.png'), 'rb')

        res = self.client.post(url, {'upload_image': filehandle})
        response_json = json.loads(res.content)
        assert any(e == msg for e in response_json['errors'])

    def test_icon_animated(self):
        self.check_image_animated(self.icon_upload,
                                  'Icons cannot be animated.')

    def test_screenshot_animated(self):
        self.check_image_animated(self.preview_upload,
                                  'Images cannot be animated.')

    @mock.patch('lib.video.ffmpeg.Video')
    @mock.patch('mkt.developers.utils.video_library')
    def add(self, handle, Video, video_library, num=1):
        data_formset = self.formset_media(upload_image=handle)
        r = self.client.post(self.preview_upload, data_formset)
        self.assertNoFormErrors(r)
        upload_hash = json.loads(r.content)['upload_hash']

        # Create and post with the formset.
        fields = []
        for i in xrange(num):
            fields.append(self.formset_new_form(upload_hash=upload_hash,
                                                position=i))
        data_formset = self.formset_media(*fields)

        r = self.client.post(self.edit_url, data_formset)
        self.assertNoFormErrors(r)

    def preview_add(self, num=1):
        self.add(open(get_image_path('preview.jpg'), 'rb'), num=num)

    @mock.patch('mimetypes.guess_type', lambda *a: ('video/webm', 'webm'))
    def preview_video_add(self, num=1):
        self.add(open(video_files['good'], 'rb'), num=num)

    @mock.patch('lib.video.ffmpeg.Video')
    @mock.patch('mkt.developers.utils.video_library')
    def add_json(self, handle, Video, video_library):
        data_formset = self.formset_media(upload_image=handle)
        result = self.client.post(self.preview_upload, data_formset)
        return json.loads(result.content)

    @mock.patch('mimetypes.guess_type', lambda *a: ('video/webm', 'webm'))
    def test_edit_preview_video_add_hash(self):
        res = self.add_json(open(video_files['good'], 'rb'))
        assert not res['errors'], res['errors']
        assert res['upload_hash'].endswith('.video-webm'), res['upload_hash']

    def test_edit_preview_add_hash(self):
        res = self.add_json(open(get_image_path('preview.jpg'), 'rb'))
        assert res['upload_hash'].endswith('.image-jpeg'), res['upload_hash']

    def test_edit_preview_add_hash_size(self):
        res = self.add_json(open(get_image_path('mozilla.png'), 'rb'))
        assert any(e.startswith('App previews ') for e in res['errors']), (
            'Small screenshot not flagged for size.')

    @mock.patch.object(settings, 'MAX_VIDEO_UPLOAD_SIZE', 1)
    @mock.patch('mimetypes.guess_type', lambda *a: ('video/webm', 'webm'))
    def test_edit_preview_video_size(self):
        res = self.add_json(open(video_files['good'], 'rb'))
        assert any(e.startswith('Please use files smaller than')
                   for e in res['errors']), (res['errors'])

    @mock.patch('lib.video.tasks.resize_video')
    @mock.patch('mimetypes.guess_type', lambda *a: ('video/webm', 'webm'))
    def test_edit_preview_video_add(self, resize_video):
        eq_(self.get_webapp().previews.count(), 0)
        self.preview_video_add()
        eq_(self.get_webapp().previews.count(), 1)

    def test_edit_preview_add(self):
        eq_(self.get_webapp().previews.count(), 0)
        self.preview_add()
        eq_(self.get_webapp().previews.count(), 1)

    def test_edit_preview_edit(self):
        self.preview_add()
        preview = self.get_webapp().previews.all()[0]
        edited = {'upload_hash': 'xxx',
                  'id': preview.id,
                  'position': preview.position,
                  'file_upload': None}

        data_formset = self.formset_media(edited, initial_count=1)

        self.client.post(self.edit_url, data_formset)

        eq_(self.get_webapp().previews.count(), 1)

    def test_edit_preview_reorder(self):
        self.preview_add(3)

        previews = list(self.get_webapp().previews.all())

        base = dict(upload_hash='xxx', file_upload=None)

        # Three preview forms were generated; mix them up here.
        a = dict(position=1, id=previews[2].id)
        b = dict(position=2, id=previews[0].id)
        c = dict(position=3, id=previews[1].id)
        a.update(base)
        b.update(base)
        c.update(base)

        # Add them in backwards ("third", "second", "first")
        data_formset = self.formset_media({}, *(c, b, a), initial_count=3)
        eq_(data_formset['files-0-id'], previews[1].id)
        eq_(data_formset['files-1-id'], previews[0].id)
        eq_(data_formset['files-2-id'], previews[2].id)

        self.client.post(self.edit_url, data_formset)

        # They should come out "first", "second", "third".
        eq_(self.get_webapp().previews.all()[0].id, previews[2].id)
        eq_(self.get_webapp().previews.all()[1].id, previews[0].id)
        eq_(self.get_webapp().previews.all()[2].id, previews[1].id)

    def test_edit_preview_delete(self):
        self.preview_add()
        self.preview_add()
        orig_previews = self.get_webapp().previews.all()

        # Delete second preview. Keep the first.
        edited = {'DELETE': 'checked',
                  'upload_hash': 'xxx',
                  'id': orig_previews[1].id,
                  'position': 0,
                  'file_upload': None}
        ctx = self.client.get(self.edit_url).context

        first = initial(ctx['preview_form'].forms[0])
        first['upload_hash'] = 'xxx'
        data_formset = self.formset_media(edited, *(first,), initial_count=2)

        r = self.client.post(self.edit_url, data_formset)
        self.assertNoFormErrors(r)

        # First one should still be there.
        eq_(list(self.get_webapp().previews.all()), [orig_previews[0]])

    def test_edit_preview_add_another(self):
        self.preview_add()
        self.preview_add()
        eq_(self.get_webapp().previews.count(), 2)

    def test_edit_preview_add_two(self):
        self.preview_add(2)
        eq_(self.get_webapp().previews.count(), 2)

    def test_screenshot_video_required(self):
        r = self.client.post(self.edit_url, self.formset_media())
        eq_(r.context['preview_form'].non_form_errors(),
            ['You must upload at least one screenshot or video.'])

    def test_screenshot_with_icon(self):
        self.preview_add()
        preview = self.get_webapp().previews.all()[0]
        edited = {'upload_hash': '', 'id': preview.id}
        data_formset = self.formset_media(edited, initial_count=1)
        data_formset.update(icon_type='image/png', icon_upload_hash='')

        r = self.client.post(self.edit_url, data_formset)
        self.assertNoFormErrors(r)


class TestEditDetails(TestEdit):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        super(TestEditDetails, self).setUp()
        self.url = self.get_url('details')
        self.edit_url = self.get_url('details', edit=True)

    def get_dict(self, **kw):
        data = dict(default_locale='en-US',
                    homepage='http://twitter.com/fligtarsmom',
                    privacy_policy="fligtar's mom does <em>not</em> share "
                                   "your data with third parties.")
        data.update(kw)
        return data

    def test_form_url(self):
        self.check_form_url('details')

    def test_edit(self):
        data = self.get_dict()
        r = self.client.post(self.edit_url, data)
        self.assertNoFormErrors(r)
        self.compare(data)

    def test_privacy_policy_xss(self):
        self.webapp.privacy_policy = ("We\n<b>own</b>your"
                                      "<script>alert('soul')</script>")
        self.webapp.save()
        r = self.client.get(self.url)
        eq_(pq(r.content)('#addon-privacy-policy span[lang]').html(),
            "We<br/><b>own</b>your&lt;script&gt;"
            "alert('soul')&lt;/script&gt;")

    def test_edit_exclude_optional_fields(self):
        data = self.get_dict()
        data.update(default_locale='en-US', homepage='',
                    privacy_policy='we sell your data to everyone')

        r = self.client.post(self.edit_url, data)
        self.assertNoFormErrors(r)
        self.compare(data)

    def test_edit_default_locale_required_trans(self):
        # name and description are required in the new locale.

        def missing(f):
            return error % ', '.join(map(repr, f))

        data = self.get_dict()
        data.update(description='bullocks',
                    homepage='http://omg.org/yes',
                    privacy_policy='your data is delicious')
        fields = ['name', 'description']
        error = ('Before changing your default locale you must have a name '
                 'and description in that locale. You are missing %s.')

        data.update(default_locale='pt-BR')
        r = self.client.post(self.edit_url, data)
        self.assertFormError(r, 'form', None, missing(fields))

        # Now we have a name.
        self.webapp.name = {'pt-BR': 'pt-BR name'}
        self.webapp.save()
        fields.remove('name')
        r = self.client.post(self.edit_url, data)
        self.assertFormError(r, 'form', None, missing(fields))

    def test_edit_default_locale_frontend_error(self):
        data = self.get_dict()
        data.update(description='xx', homepage='http://google.com',
                    default_locale='pt-BR', privacy_policy='pp')
        rp = self.client.post(self.edit_url, data)
        self.assertContains(rp,
                            'Before changing your default locale you must')

    def test_edit_locale(self):
        self.webapp.update(default_locale='en-US')
        r = self.client.get(self.url)
        eq_(pq(r.content)('.addon_edit_locale').eq(0).text(),
            'English (US)')

    def test_homepage_url_optional(self):
        r = self.client.post(self.edit_url, self.get_dict(homepage=''))
        self.assertNoFormErrors(r)

    def test_homepage_url_invalid(self):
        r = self.client.post(self.edit_url,
                             self.get_dict(homepage='xxx'))
        self.assertFormError(r, 'form', 'homepage', 'Enter a valid URL.')

    def test_games_already_excluded_in_brazil(self):
        AER.objects.create(addon=self.webapp, region=mkt.regions.BRA.id)
        games = 'games'

        r = self.client.post(
            self.edit_url, self.get_dict(categories=[games]))
        self.assertNoFormErrors(r)
        eq_(list(AER.objects.filter(addon=self.webapp)
                            .values_list('region', flat=True)),
            [mkt.regions.BRA.id])


class TestEditSupport(TestEdit):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        super(TestEditSupport, self).setUp()
        self.url = self.get_url('support')
        self.edit_url = self.get_url('support', edit=True)

    def test_form_url(self):
        self.check_form_url('support')

    def test_edit_support(self):
        data = dict(support_email='sjobs@apple.com',
                    support_url='http://apple.com/')

        res = self.client.post(self.edit_url, data)
        self.assertNoFormErrors(res)
        self.compare(data)

    def test_edit_support_required(self):
        res = self.client.post(self.edit_url, {})
        self.assertFormError(
            res, 'form', 'support',
            'You must provide either a website, an email, or both.')

    def test_edit_support_only_one_is_required(self):
        data = dict(support_email='sjobs@apple.com', support_url='')
        res = self.client.post(self.edit_url, data)
        self.assertNoFormErrors(res)
        self.compare(data)

        data = dict(support_email='', support_url='http://my.support.us')
        res = self.client.post(self.edit_url, data)
        self.assertNoFormErrors(res)
        self.compare(data)

    def test_edit_support_errors(self):
        data = dict(support_email='', support_url='http://my')
        res = self.client.post(self.edit_url, data)
        self.assertFormError(res, 'form', 'support_url',
                             'Enter a valid URL.')
        ok_(not pq(res.content)('#trans-support_email+.errorlist'))
        ok_(pq(res.content)('#trans-support_url+.errorlist'))

        data = dict(support_email='test', support_url='')
        res = self.client.post(self.edit_url, data)
        self.assertFormError(res, 'form', 'support_email',
                             'Enter a valid email address.')
        ok_(pq(res.content)('#trans-support_email+.errorlist'))
        ok_(not pq(res.content)('#trans-support_url+.errorlist'))


class TestEditTechnical(TestEdit):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        super(TestEditTechnical, self).setUp()
        self.url = self.get_url('technical')
        self.edit_url = self.get_url('technical', edit=True)
        self.latest_file = self.get_webapp().latest_version.all_files[0]

    def test_form_url(self):
        self.check_form_url('technical')

    def test_toggle_flash(self):
        # Turn flash on.
        r = self.client.post(self.edit_url, formset(**{'flash': 'on'}))
        self.assertNoFormErrors(r)
        self.latest_file.reload()
        self.compare({'uses_flash': True}, instance=self.latest_file)

        # And off.
        r = self.client.post(self.edit_url, formset(**{'flash': ''}))
        self.latest_file.reload()
        self.compare({'uses_flash': False}, instance=self.latest_file)

    def test_toggle_flash_rejected(self):
        # Reject the app.
        app = self.get_webapp()
        app.update(status=mkt.STATUS_REJECTED)
        app.versions.latest().all_files[0].update(status=mkt.STATUS_DISABLED)
        app.update_version()

        self.test_toggle_flash()

    def test_public_stats(self):
        o = ActivityLog.objects
        eq_(o.count(), 0)

        eq_(self.webapp.public_stats, False)
        assert not self.webapp.public_stats, (
            'Unexpectedly found public stats for app. Says Basta.')

        r = self.client.post(self.edit_url, formset(public_stats=True))
        self.assertNoFormErrors(r)

        self.compare({'public_stats': True})
        eq_(o.filter(action=mkt.LOG.EDIT_PROPERTIES.id).count(), 1)

    def test_features_hosted(self):
        data_on = {'has_contacts': True}
        data_off = {'has_contacts': False}

        assert not RereviewQueue.objects.filter(addon=self.webapp).exists()

        # Turn contacts on.
        r = self.client.post(self.edit_url, formset(**data_on))
        self.assertNoFormErrors(r)
        self.compare_features(data_on)

        # And turn it back off.
        r = self.client.post(self.edit_url, formset(**data_off))
        self.assertNoFormErrors(r)
        self.compare_features(data_off)

        # Changing features must trigger re-review.
        assert RereviewQueue.objects.filter(addon=self.webapp).exists()

    def test_features_hosted_app_rejected(self):
        # Reject the app.
        app = self.get_webapp()
        app.update(status=mkt.STATUS_REJECTED)
        app.versions.latest().all_files[0].update(status=mkt.STATUS_DISABLED)
        app.update_version()

        assert not RereviewQueue.objects.filter(addon=self.webapp).exists()

        data_on = {'has_contacts': True}
        data_off = {'has_contacts': False}

        # Display edit technical page
        r = self.client.get(self.edit_url)
        eq_(r.status_code, 200)

        # Turn contacts on.
        r = self.client.post(self.edit_url, formset(**data_on))
        app = self.get_webapp()
        self.assertNoFormErrors(r)
        self.compare_features(data_on, version=app.latest_version)

        # Display edit technical page again, is the feature on ?
        r = self.client.get(self.edit_url)
        eq_(r.status_code, 200)
        ok_(pq(r.content)('#id_has_contacts:checked'))

        # And turn it back off.
        r = self.client.post(self.edit_url, formset(**data_off))
        app = self.get_webapp()
        self.assertNoFormErrors(r)
        self.compare_features(data_off, version=app.latest_version)

        # Changing features on a rejected app must NOT trigger re-review.
        assert not RereviewQueue.objects.filter(addon=self.webapp).exists()


class TestAdmin(TestEdit):
    fixtures = TestEdit.fixtures

    def setUp(self):
        super(TestAdmin, self).setUp()
        self.url = self.get_url('admin')
        self.edit_url = self.get_url('admin', edit=True)
        self.webapp = self.get_webapp()
        self.login('admin@mozilla.com')

    def log_in_user(self):
        self.login(self.user.email)

    def log_in_with(self, rules):
        user = UserProfile.objects.get(email='regular@mozilla.com')
        group = Group.objects.create(name='Whatever', rules=rules)
        GroupUser.objects.create(group=group, user=user)
        self.login(user.email)


class TestAdminSettings(TestAdmin):
    fixtures = TestEdit.fixtures

    def test_form_url(self):
        self.check_form_url('admin')

    def test_overview_visible_as_admin(self):
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        eq_(pq(r.content)('form').length, 1)
        assert not r.context.get('form'), (
            'Admin Settings form should not be in context')

    def test_overview_forbidden_for_nonadmin(self):
        self.log_in_user()
        eq_(self.client.head(self.url).status_code, 403)

    def test_edit_get_as_admin(self):
        r = self.client.get(self.edit_url)
        eq_(r.status_code, 200)
        eq_(pq(r.content)('form').length, 1)
        assert r.context.get('form'), 'Admin Settings form expected in context'

    def test_edit_post_as_admin(self):
        # There are errors, but I don't care. I just want to see if I can POST.
        eq_(self.client.post(self.edit_url).status_code, 200)

    def test_edit_no_get_as_nonadmin(self):
        self.log_in_user()
        eq_(self.client.get(self.edit_url).status_code, 403)

    def test_edit_no_post_as_nonadmin(self):
        self.log_in_user()
        eq_(self.client.post(self.edit_url).status_code, 403)

    def post_contact(self, **kw):
        data = {'position': '1',
                'upload_hash': 'abcdef',
                'mozilla_contact': 'a@mozilla.com'}
        data.update(kw)
        return self.client.post(self.edit_url, data)

    def test_mozilla_contact(self):
        self.post_contact()
        webapp = self.get_webapp()
        eq_(webapp.mozilla_contact, 'a@mozilla.com')

    def test_mozilla_contact_cleared(self):
        self.post_contact(mozilla_contact='')
        webapp = self.get_webapp()
        eq_(webapp.mozilla_contact, '')

    def test_mozilla_contact_invalid(self):
        r = self.post_contact(
            mozilla_contact='<script>alert("xss")</script>@mozilla.com')
        webapp = self.get_webapp()
        self.assertFormError(r, 'form', 'mozilla_contact',
                             'Enter a valid email address.')
        eq_(webapp.mozilla_contact, '')

    def test_vip_app_toggle(self):
        # Turn on.
        data = {
            'position': 1,  # Required, useless in this test.
            'vip_app': 'on'
        }
        r = self.client.post(self.edit_url, data)
        self.assertNoFormErrors(r)
        self.compare({'vip_app': True})

        # And off.
        data.update({'vip_app': ''})
        r = self.client.post(self.edit_url, data)
        self.compare({'vip_app': False})

    def test_priority_review_toggle(self):
        # Turn on.
        data = {
            'position': 1,  # Required, useless in this test.
            'priority_review': 'on'
        }
        r = self.client.post(self.edit_url, data)
        self.assertNoFormErrors(r)
        self.compare({'priority_review': True})

        # And off.
        data = {'position': 1}
        r = self.client.post(self.edit_url, data)
        self.compare({'priority_review': False})

    def test_staff(self):
        # Staff and Support Staff should have Apps:Configure.
        self.log_in_with('Apps:Configure')

        # Test GET.
        r = self.client.get(self.edit_url)
        eq_(r.status_code, 200)
        eq_(pq(r.content)('form').length, 1)
        assert r.context.get('form'), 'Admin Settings form expected in context'

        # Test POST. Ignore errors.
        eq_(self.client.post(self.edit_url).status_code, 200)

    def test_developer(self):
        # Developers have read-only on admin section.
        self.log_in_with('Apps:ViewConfiguration')

        # Test GET.
        r = self.client.get(self.edit_url)
        eq_(r.status_code, 200)
        eq_(pq(r.content)('form').length, 1)
        assert r.context.get('form'), 'Admin Settings form expected in context'

        # Test POST. Ignore errors.
        eq_(self.client.post(self.edit_url).status_code, 403)

    def test_banner_region_view(self):
        self.log_in_with('Apps:ViewConfiguration')
        geodata = self.get_webapp().geodata
        geodata.banner_message = u'Exclusive message ! Only for AR/BR !'
        geodata.banner_regions = [mkt.regions.BRA.id, mkt.regions.ARG.id]
        geodata.save()
        res = self.client.get(self.url)

        eq_(pq(res.content)('#id_banner_message').text(),
            unicode(geodata.banner_message))
        eq_(pq(res.content)('#id_banner_regions').text(), u'Argentina, Brazil')

    def test_banner_region_edit(self):
        self.log_in_with('Apps:ViewConfiguration')
        geodata = self.webapp.geodata
        geodata.banner_message = u'Exclusive message ! Only for AR/BR !'
        geodata.banner_regions = [mkt.regions.BRA.id, mkt.regions.ARG.id]
        geodata.save()
        AER.objects.create(addon=self.webapp, region=mkt.regions.USA.id)

        res = self.client.get(self.edit_url)
        eq_(res.status_code, 200)
        doc = pq(res.content)
        inputs = doc.find('input[type=checkbox][name=banner_regions]')
        eq_(inputs.length, len(mkt.regions.REGIONS_CHOICES_ID))

        checked = doc.find('#id_banner_regions input[type=checkbox]:checked')
        eq_(checked.length, 2)
        eq_(checked[0].name, 'banner_regions')
        eq_(checked[0].value, unicode(mkt.regions.ARG.id))
        eq_(pq(checked[0]).parents('li').attr('data-region'),
            unicode(mkt.regions.ARG.id))
        eq_(checked[1].name, 'banner_regions')
        eq_(checked[1].value, unicode(mkt.regions.BRA.id))
        eq_(pq(checked[1]).parents('li').attr('data-region'),
            unicode(mkt.regions.BRA.id))

    def test_banner_region_edit_post(self):
        data = {
            'position': 1,  # Required, useless in this test.
            'banner_regions': [unicode(mkt.regions.BRA.id),
                               unicode(mkt.regions.ESP.id)],
            'banner_message_en-us': u'Oh Hai.',
        }
        res = self.client.post(self.edit_url, data)
        eq_(res.status_code, 200)
        geodata = self.webapp.geodata.reload()
        eq_(geodata.banner_message, data['banner_message_en-us'])
        eq_(geodata.banner_regions, [mkt.regions.BRA.id, mkt.regions.ESP.id])


class TestPromoUpload(TestAdmin):
    fixtures = TestEdit.fixtures

    def post(self, **kw):
        data = {'position': '1',
                'upload_hash': 'abcdef'}
        data.update(kw)
        self.client.post(self.edit_url, data)

    def test_add(self):
        self.post()

        webapp = self.get_webapp()

        eq_(webapp.previews.count(), 1)
        eq_(list(webapp.get_previews()), [])

        promo = webapp.get_promo()
        eq_(promo.position, -1)

    def test_delete(self):
        self.post()
        assert self.get_webapp().get_promo()

        self.post(DELETE=True)
        assert not self.get_webapp().get_promo()


class TestEditVersion(TestEdit):
    fixtures = fixture('group_admin', 'user_999', 'user_admin',
                       'user_admin_group', 'webapp_337141')

    def setUp(self):
        self.webapp = self.get_webapp()
        self.webapp.update(is_packaged=True)
        self.version_pk = self.webapp.latest_version.pk
        self.url = reverse('mkt.developers.apps.versions.edit', kwargs={
            'version_id': self.version_pk,
            'app_slug': self.webapp.app_slug
        })
        self.user = UserProfile.objects.get(email='steamcube@mozilla.com')
        self.login(self.user)

    def test_post(self, **kwargs):
        data = {'releasenotes_init': '',
                'releasenotes_en-us': 'Hot new version',
                'approvalnotes': 'The release notes are true.',
                'has_audio': False,
                'has_apps': False}
        data.update(kwargs)
        req = self.client.post(self.url, data)
        eq_(req.status_code, 302)
        version = Version.objects.no_cache().get(pk=self.version_pk)
        eq_(version.releasenotes, data['releasenotes_en-us'])
        eq_(version.approvalnotes, data['approvalnotes'])
        return version

    def test_approval_notes_comm_thread(self):
        # With empty note.
        self.test_post(approvalnotes='')
        eq_(CommunicationNote.objects.count(), 0)

        self.test_post(approvalnotes='abc')
        notes = CommunicationNote.objects.all()
        eq_(notes.count(), 1)
        eq_(notes[0].body, 'abc')
        eq_(notes[0].note_type, comm.DEVELOPER_VERSION_NOTE_FOR_REVIEWER)

    def test_existing_features_initial_form_data(self):
        features = self.webapp.current_version.features
        features.update(has_audio=True, has_apps=True)
        r = self.client.get(self.url)
        eq_(r.context['appfeatures_form'].initial,
            dict(id=features.id, **features.to_dict()))

    @mock.patch('mkt.webapps.tasks.index_webapps.delay')
    def test_new_features(self, index_webapps):
        assert not RereviewQueue.objects.filter(addon=self.webapp).exists()
        index_webapps.reset_mock()
        old_modified = self.webapp.modified

        # Turn a feature on.
        version = self.test_post(has_audio=True)
        ok_(version.features.has_audio)
        ok_(not version.features.has_apps)

        # Addon modified date must have changed.
        addon = self.get_webapp()
        ok_(addon.modified > old_modified)
        old_modified = self.webapp.modified

        index_webapps.reset_mock()

        # Then turn the feature off.
        version = self.test_post(has_audio=False)
        ok_(not version.features.has_audio)
        ok_(not version.features.has_apps)

        # Changing features must trigger re-review.
        assert RereviewQueue.objects.filter(addon=self.webapp).exists()

        # Addon modified date must have changed.
        addon = self.get_webapp()
        ok_(addon.modified > old_modified)

        # Changing features must trigger a reindex.
        eq_(index_webapps.call_count, 1)

    def test_features_uncheck_all(self):
        version = self.test_post(has_audio=True)
        ok_(version.features.has_audio)
        req = self.client.post(self.url, {})  # Empty POST should uncheck all.
        eq_(req.status_code, 302)
        version.features.reload()
        ok_(not version.features.has_audio)

    def test_correct_version_features(self):
        new_version = self.webapp.latest_version.update(id=self.version_pk + 1)
        self.webapp.update(_latest_version=new_version)
        self.test_new_features()

    def test_publish_checkbox_presence(self):
        res = self.client.get(self.url)
        ok_(not pq(res.content)('#id_publish_immediately'))

        self.webapp.latest_version.files.update(status=mkt.STATUS_PENDING)
        res = self.client.get(self.url)
        ok_(pq(res.content)('#id_publish_immediately'))
