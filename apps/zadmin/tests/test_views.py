# -*- coding: utf-8 -*-
import csv
import json
from cStringIO import StringIO

from django.core import mail, management
from django.core.cache import cache

import mock
from nose.tools import eq_
from pyquery import PyQuery as pq

import amo
import amo.tests
from addons.models import Addon
from amo.urlresolvers import reverse
from amo.utils import urlparams
from files.models import File
from mkt.access.models import Group, GroupUser
from users.models import UserProfile
from versions.models import Version
from zadmin.forms import DevMailerForm
from zadmin.models import EmailPreviewTopic


class TestEmailPreview(amo.tests.TestCase):
    fixtures = ['base/addon_3615', 'base/users']

    def setUp(self):
        assert self.client.login(username='admin@mozilla.com',
                                 password='password')
        addon = Addon.objects.get(pk=3615)
        self.topic = EmailPreviewTopic(addon)

    def test_csv(self):
        self.topic.send_mail('the subject', u'Hello Ivan Krsti\u0107',
                             from_email='admin@mozilla.org',
                             recipient_list=['funnyguy@mozilla.org'])
        r = self.client.get(reverse('zadmin.email_preview_csv',
                            args=[self.topic.topic]))
        eq_(r.status_code, 200)
        rdr = csv.reader(StringIO(r.content))
        eq_(rdr.next(), ['from_email', 'recipient_list', 'subject', 'body'])
        eq_(rdr.next(), ['admin@mozilla.org', 'funnyguy@mozilla.org',
                         'the subject', 'Hello Ivan Krsti\xc4\x87'])


class TestLookup(amo.tests.TestCase):
    fixtures = ['base/users']

    def setUp(self):
        assert self.client.login(username='admin@mozilla.com',
                                 password='password')
        self.user = UserProfile.objects.get(pk=999)
        self.url = reverse('zadmin.search', args=['users', 'userprofile'])

    def test_logged_out(self):
        self.client.logout()
        eq_(self.client.get('%s?q=admin' % self.url).status_code, 403)

    def check_results(self, q, expected):
        res = self.client.get(urlparams(self.url, q=q))
        eq_(res.status_code, 200)
        content = json.loads(res.content)
        eq_(len(content), len(expected))
        ids = [int(c['value']) for c in content]
        emails = [u'%s' % c['label'] for c in content]
        for d in expected:
            id = d['value']
            email = u'%s' % d['label']
            assert id in ids, (
                'Expected user ID "%s" not found' % id)
            assert email in emails, (
                'Expected username "%s" not found' % email)

    def test_lookup_wrong_model(self):
        self.url = reverse('zadmin.search', args=['doesnt', 'exist'])
        res = self.client.get(urlparams(self.url, q=''))
        eq_(res.status_code, 404)

    def test_lookup_empty(self):
        users = UserProfile.objects.values('id', 'email')
        self.check_results('', [dict(
            value=u['id'], label=u['email']) for u in users])

    def test_lookup_by_id(self):
        self.check_results(self.user.id, [dict(value=self.user.id,
                                               label=self.user.email)])

    def test_lookup_by_email(self):
        self.check_results(self.user.email, [dict(value=self.user.id,
                                                  label=self.user.email)])

    def test_lookup_by_username(self):
        self.check_results(self.user.username, [dict(value=self.user.id,
                                                     label=self.user.email)])


class TestAddonSearch(amo.tests.ESTestCase):
    fixtures = ['base/users', 'base/addon_3615']

    def setUp(self):
        self.reindex(Addon)
        assert self.client.login(username='admin@mozilla.com',
                                 password='password')
        self.url = reverse('zadmin.addon-search')

    @mock.patch('mkt.webapps.tasks.index_webapps')
    def test_lookup_app(self, index_webapps_mock):
        # Load the Webapp fixture here, as loading it in the
        # TestAddonSearch.fixtures would trigger the reindex, and fail, as
        # this is an AMO test.
        management.call_command('loaddata', 'base/337141-steamcube')
        index_webapps_mock.assert_called()

        res = self.client.get(urlparams(self.url, q='steamcube'))
        eq_(res.status_code, 200)
        links = pq(res.content)('form + h3 + ul li a')
        eq_(len(links), 0)
        if any(li.text().contains('Steamcube') for li in links):
            raise AssertionError('Did not expect webapp in results.')

    def test_lookup_addon(self):
        res = self.client.get(urlparams(self.url, q='delicious'))
        # There's only one result, so it should just forward us to that page.
        eq_(res.status_code, 302)


class TestAddonAdmin(amo.tests.TestCase):
    fixtures = ['base/users', 'base/337141-steamcube', 'base/addon_3615']

    def setUp(self):
        assert self.client.login(username='admin@mozilla.com',
                                 password='password')
        self.url = reverse('admin:addons_addon_changelist')

    def test_no_webapps(self):
        res = self.client.get(self.url)
        doc = pq(res.content)
        rows = doc('#result_list tbody tr')
        eq_(rows.length, 1)
        eq_(rows.find('a').attr('href'),
            '/en-US/admin/models/addons/addon/3615/')


class TestAddonManagement(amo.tests.TestCase):
    fixtures = ['base/addon_3615', 'base/users']

    def setUp(self):
        self.addon = Addon.objects.get(pk=3615)
        self.url = reverse('zadmin.addon_manage', args=[self.addon.slug])
        self.client.login(username='admin@mozilla.com', password='password')

    def _form_data(self, data=None):
        initial_data = {
            'status': '4',
            'highest_status': '4',
            'form-0-status': '4',
            'form-0-id': '67442',
            'form-TOTAL_FORMS': '1',
            'form-INITIAL_FORMS': '1',
        }
        if data:
            initial_data.update(data)
        return initial_data

    def test_addon_status_change(self):
        data = self._form_data({'status': '2'})
        r = self.client.post(self.url, data, follow=True)
        eq_(r.status_code, 200)
        addon = Addon.objects.get(pk=3615)
        eq_(addon.status, 2)

    def test_addon_file_status_change(self):
        data = self._form_data({'form-0-status': '2'})
        r = self.client.post(self.url, data, follow=True)
        eq_(r.status_code, 200)
        file = File.objects.get(pk=67442)
        eq_(file.status, 2)

    @mock.patch.object(File, 'file_path',
                       amo.tests.AMOPaths().file_fixture_path(
                           'delicious_bookmarks-2.1.106-fx.xpi'))
    def test_regenerate_hash(self):
        version = Version.objects.create(addon_id=3615)
        file = File.objects.create(
            filename='delicious_bookmarks-2.1.106-fx.xpi', version=version)

        r = self.client.post(reverse('zadmin.recalc_hash', args=[file.id]))
        eq_(json.loads(r.content)[u'success'], 1)

        file = File.objects.get(pk=file.id)

        assert file.size, 'File size should not be zero'
        assert file.hash, 'File hash should not be empty'

    @mock.patch.object(File, 'file_path',
                       amo.tests.AMOPaths().file_fixture_path(
                           'delicious_bookmarks-2.1.106-fx.xpi'))
    def test_regenerate_hash_get(self):
        """ Don't allow GET """
        version = Version.objects.create(addon_id=3615)
        file = File.objects.create(
            filename='delicious_bookmarks-2.1.106-fx.xpi', version=version)

        r = self.client.get(reverse('zadmin.recalc_hash', args=[file.id]))
        eq_(r.status_code, 405)  # GET out of here


class TestMemcache(amo.tests.TestCase):
    fixtures = ['base/addon_3615', 'base/users']

    def setUp(self):
        self.url = reverse('zadmin.memcache')
        cache.set('foo', 'bar')
        self.client.login(username='admin@mozilla.com', password='password')

    def test_login(self):
        self.client.logout()
        eq_(self.client.get(self.url).status_code, 302)

    def test_can_clear(self):
        self.client.post(self.url, {'yes': 'True'})
        eq_(cache.get('foo'), None)

    def test_cant_clear(self):
        self.client.post(self.url, {'yes': 'False'})
        eq_(cache.get('foo'), 'bar')


class TestElastic(amo.tests.ESTestCase):
    fixtures = ['base/addon_3615', 'base/users']

    def setUp(self):
        self.url = reverse('zadmin.elastic')
        self.client.login(username='admin@mozilla.com', password='password')

    def test_login(self):
        self.client.logout()
        self.assertRedirects(self.client.get(self.url),
            reverse('users.login') + '?to=/en-US/admin/elastic')


class TestEmailDevs(amo.tests.TestCase):
    fixtures = ['base/addon_3615', 'base/users']

    def setUp(self):
        self.login('admin')
        self.addon = Addon.objects.get(pk=3615)

    def post(self, recipients='payments', subject='subject', message='msg',
             preview_only=False):
        return self.client.post(reverse('zadmin.email_devs'),
                                dict(recipients=recipients, subject=subject,
                                     message=message,
                                     preview_only=preview_only))

    def test_preview(self):
        res = self.post(preview_only=True)
        self.assertNoFormErrors(res)
        preview = EmailPreviewTopic(topic='email-devs')
        eq_([e.recipient_list for e in preview.filter()], ['del@icio.us'])
        eq_(len(mail.outbox), 0)

    def test_only_apps_with_payments(self):
        self.addon.update(type=amo.ADDON_WEBAPP,
                          premium_type=amo.ADDON_PREMIUM)
        res = self.post(recipients='payments')
        self.assertNoFormErrors(res)
        eq_(len(mail.outbox), 1)

        mail.outbox = []
        self.addon.update(status=amo.STATUS_PENDING)
        res = self.post(recipients='payments')
        self.assertNoFormErrors(res)
        eq_(len(mail.outbox), 1)

        mail.outbox = []
        self.addon.update(status=amo.STATUS_DELETED)
        res = self.post(recipients='payments')
        self.assertNoFormErrors(res)
        eq_(len(mail.outbox), 0)

    def test_only_free_apps_with_new_regions(self):
        self.addon.update(type=amo.ADDON_WEBAPP)
        res = self.post(recipients='free_apps_region_enabled')
        self.assertNoFormErrors(res)
        eq_(len(mail.outbox), 0)
        mail.outbox = []
        res = self.post(recipients='free_apps_region_disabled')
        self.assertNoFormErrors(res)
        eq_(len(mail.outbox), 1)

        mail.outbox = []
        self.addon.update(enable_new_regions=True)
        res = self.post(recipients='free_apps_region_enabled')
        self.assertNoFormErrors(res)
        eq_(len(mail.outbox), 1)
        mail.outbox = []
        res = self.post(recipients='free_apps_region_disabled')
        self.assertNoFormErrors(res)
        eq_(len(mail.outbox), 0)

    def test_only_apps_with_payments_and_new_regions(self):
        self.addon.update(type=amo.ADDON_WEBAPP,
                          premium_type=amo.ADDON_PREMIUM)
        res = self.post(recipients='payments_region_enabled')
        self.assertNoFormErrors(res)
        eq_(len(mail.outbox), 0)
        mail.outbox = []
        res = self.post(recipients='payments_region_disabled')
        self.assertNoFormErrors(res)
        eq_(len(mail.outbox), 1)

        mail.outbox = []
        self.addon.update(enable_new_regions=True)
        res = self.post(recipients='payments_region_enabled')
        self.assertNoFormErrors(res)
        eq_(len(mail.outbox), 1)
        mail.outbox = []
        res = self.post(recipients='payments_region_disabled')
        self.assertNoFormErrors(res)
        eq_(len(mail.outbox), 0)

    def test_only_desktop_apps(self):
        from addons.models import AddonDeviceType
        self.addon.update(type=amo.ADDON_WEBAPP)
        AddonDeviceType.objects.create(addon=self.addon,
            device_type=amo.DEVICE_MOBILE.id)
        res = self.post(recipients='desktop_apps')
        self.assertNoFormErrors(res)
        eq_(len(mail.outbox), 0)

        mail.outbox = []
        AddonDeviceType.objects.create(addon=self.addon,
            device_type=amo.DEVICE_DESKTOP.id)
        res = self.post(recipients='desktop_apps')
        self.assertNoFormErrors(res)
        eq_(len(mail.outbox), 1)

        mail.outbox = []
        self.addon.update(status=amo.STATUS_PENDING)
        res = self.post(recipients='desktop_apps')
        self.assertNoFormErrors(res)
        eq_(len(mail.outbox), 1)

        mail.outbox = []
        self.addon.update(status=amo.STATUS_DELETED)
        res = self.post(recipients='desktop_apps')
        self.assertNoFormErrors(res)
        eq_(len(mail.outbox), 0)

    def test_only_apps(self):
        self.addon.update(type=amo.ADDON_WEBAPP)
        res = self.post(recipients='apps')
        self.assertNoFormErrors(res)
        eq_(len(mail.outbox), 1)

    def test_only_extensions(self):
        self.addon.update(type=amo.ADDON_EXTENSION)
        res = self.post(recipients='all_extensions')
        self.assertNoFormErrors(res)
        eq_(len(mail.outbox), 1)

    def test_ignore_deleted_always(self):
        self.addon.update(status=amo.STATUS_DELETED)
        for name, label in DevMailerForm._choices:
            res = self.post(recipients=name)
            self.assertNoFormErrors(res)
            eq_(len(mail.outbox), 0)

    def test_exclude_pending_for_addons(self):
        self.addon.update(status=amo.STATUS_PENDING)
        for name, label in DevMailerForm._choices:
            if name in ('payments', 'desktop_apps'):
                continue
            res = self.post(recipients=name)
            self.assertNoFormErrors(res)
            eq_(len(mail.outbox), 0)


class TestPerms(amo.tests.TestCase):
    fixtures = ['base/users', 'base/apps']

    def test_admin_user(self):
        # Admin should see views with Django's perm decorator and our own.
        assert self.client.login(username='admin@mozilla.com',
                                 password='password')
        eq_(self.client.get(reverse('zadmin.index')).status_code, 200)
        eq_(self.client.get(reverse('zadmin.settings')).status_code, 200)
        eq_(self.client.get(reverse('zadmin.addon-search')).status_code, 200)

    def test_staff_user(self):
        # Staff users have some privileges.
        user = UserProfile.objects.get(email='regular@mozilla.com')
        group = Group.objects.create(name='Staff', rules='AdminTools:View')
        GroupUser.objects.create(group=group, user=user)
        assert self.client.login(username='regular@mozilla.com',
                                 password='password')
        eq_(self.client.get(reverse('zadmin.index')).status_code, 200)
        eq_(self.client.get(reverse('zadmin.settings')).status_code, 200)
        eq_(self.client.get(reverse('zadmin.addon-search')).status_code, 200)

    def test_sr_reviewers_user(self):
        # Sr Reviewers users have only a few privileges.
        user = UserProfile.objects.get(email='regular@mozilla.com')
        group = Group.objects.create(name='Sr Reviewer',
                                     rules='ReviewerAdminTools:View')
        GroupUser.objects.create(group=group, user=user)
        assert self.client.login(username='regular@mozilla.com',
                                 password='password')
        eq_(self.client.get(reverse('zadmin.index')).status_code, 200)
        eq_(self.client.get(reverse('zadmin.addon-search')).status_code, 200)
        eq_(self.client.get(reverse('zadmin.settings')).status_code, 403)

    def test_bulk_compat_user(self):
        # Bulk Compatibility Updaters only have access to /admin/validation/*.
        user = UserProfile.objects.get(email='regular@mozilla.com')
        group = Group.objects.create(name='Bulk Compatibility Updaters',
                                     rules='BulkValidationAdminTools:View')
        GroupUser.objects.create(group=group, user=user)
        assert self.client.login(username='regular@mozilla.com',
                                 password='password')
        eq_(self.client.get(reverse('zadmin.index')).status_code, 200)
        eq_(self.client.get(reverse('zadmin.addon-search')).status_code, 403)
        eq_(self.client.get(reverse('zadmin.settings')).status_code, 403)

    def test_unprivileged_user(self):
        # Unprivileged user.
        assert self.client.login(username='regular@mozilla.com',
                                 password='password')
        eq_(self.client.get(reverse('zadmin.index')).status_code, 403)
        eq_(self.client.get(reverse('zadmin.settings')).status_code, 403)
        eq_(self.client.get(reverse('zadmin.addon-search')).status_code, 403)
        # Anonymous users should also get a 403.
        self.client.logout()
        self.assertRedirects(self.client.get(reverse('zadmin.index')),
                             reverse('users.login') + '?to=/en-US/admin/')
