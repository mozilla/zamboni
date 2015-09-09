# -*- coding: utf-8 -*-
import csv
from cStringIO import StringIO

from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.core.urlresolvers import reverse

from nose.tools import eq_

import mkt
import mkt.site.tests
from mkt.access.models import Group, GroupUser
from mkt.reviewers.models import RereviewQueue
from mkt.site.fixtures import fixture
from mkt.users.models import UserProfile
from mkt.webapps.models import AddonDeviceType, Webapp
from mkt.zadmin.forms import DevMailerForm
from mkt.zadmin.models import EmailPreviewTopic


class TestEmailPreview(mkt.site.tests.TestCase):
    fixtures = fixture('user_admin', 'group_admin', 'user_admin_group',
                       'webapp_337141')

    def setUp(self):
        self.login('admin@mozilla.com')
        addon = Webapp.objects.get(pk=337141)
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


class TestMemcache(mkt.site.tests.TestCase):
    fixtures = fixture('user_admin', 'group_admin', 'user_admin_group')

    def setUp(self):
        self.url = reverse('zadmin.memcache')
        cache.set('foo', 'bar')
        self.login('admin@mozilla.com')

    def test_login(self):
        self.client.logout()
        eq_(self.client.get(self.url).status_code, 302)

    def test_can_clear(self):
        self.client.post(self.url, {'yes': 'True'})
        eq_(cache.get('foo'), None)

    def test_cant_clear(self):
        self.client.post(self.url, {'yes': 'False'})
        eq_(cache.get('foo'), 'bar')


class TestElastic(mkt.site.tests.ESTestCase):
    fixtures = fixture('user_admin', 'group_admin', 'user_admin_group')

    def setUp(self):
        self.url = reverse('zadmin.elastic')
        self.login('admin@mozilla.com')

    def test_login(self):
        self.client.logout()
        self.assert3xx(
            self.client.get(self.url),
            reverse('users.login') + '?to=/admin/elastic')


class TestEmailDevs(mkt.site.tests.TestCase):
    fixtures = fixture('user_admin', 'group_admin', 'user_admin_group',
                       'webapp_337141')

    def setUp(self):
        self.login('admin')
        self.addon = Webapp.objects.get(pk=337141)

    def post(self, recipients=None, subject='subject', message='msg',
             preview_only=False):
        return self.client.post(reverse('zadmin.email_devs'),
                                dict(recipients=recipients, subject=subject,
                                     message=message,
                                     preview_only=preview_only))

    def test_preview(self):
        self.addon.update(premium_type=mkt.ADDON_PREMIUM)
        res = self.post(recipients='payments', preview_only=True)
        self.assertNoFormErrors(res)
        preview = EmailPreviewTopic(topic='email-devs')
        eq_([e.recipient_list for e in preview.filter()],
            ['steamcube@mozilla.com'])
        eq_(len(mail.outbox), 0)

    def test_only_apps_with_payments(self):
        self.addon.update(premium_type=mkt.ADDON_PREMIUM)
        res = self.post(recipients='payments')
        self.assertNoFormErrors(res)
        eq_(len(mail.outbox), 1)

        mail.outbox = []
        self.addon.update(status=mkt.STATUS_PENDING)
        res = self.post(recipients='payments')
        self.assertNoFormErrors(res)
        eq_(len(mail.outbox), 1)

        mail.outbox = []
        self.addon.update(status=mkt.STATUS_DELETED)
        res = self.post(recipients='payments')
        self.assertNoFormErrors(res)
        eq_(len(mail.outbox), 0)

    def test_only_free_apps_with_new_regions(self):
        self.addon.update(enable_new_regions=False)
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
        self.addon.update(enable_new_regions=False)
        self.addon.update(premium_type=mkt.ADDON_PREMIUM)
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
        AddonDeviceType.objects.create(addon=self.addon,
                                       device_type=mkt.DEVICE_MOBILE.id)
        res = self.post(recipients='desktop_apps')
        self.assertNoFormErrors(res)
        eq_(len(mail.outbox), 0)

        mail.outbox = []
        AddonDeviceType.objects.create(addon=self.addon,
                                       device_type=mkt.DEVICE_DESKTOP.id)
        res = self.post(recipients='desktop_apps')
        self.assertNoFormErrors(res)
        eq_(len(mail.outbox), 1)

        mail.outbox = []
        self.addon.update(status=mkt.STATUS_PENDING)
        res = self.post(recipients='desktop_apps')
        self.assertNoFormErrors(res)
        eq_(len(mail.outbox), 1)

        mail.outbox = []
        self.addon.update(status=mkt.STATUS_DELETED)
        res = self.post(recipients='desktop_apps')
        self.assertNoFormErrors(res)
        eq_(len(mail.outbox), 0)

    def test_only_apps(self):
        res = self.post(recipients='apps')
        self.assertNoFormErrors(res)
        eq_(len(mail.outbox), 1)

    def test_ignore_deleted_always(self):
        self.addon.update(status=mkt.STATUS_DELETED)
        for name, label in DevMailerForm._choices:
            res = self.post(recipients=name)
            self.assertNoFormErrors(res)
            eq_(len(mail.outbox), 0)

    def test_exclude_pending_for_addons(self):
        self.addon.update(status=mkt.STATUS_PENDING)
        for name, label in DevMailerForm._choices:
            if name in ('payments', 'desktop_apps'):
                continue
            res = self.post(recipients=name)
            self.assertNoFormErrors(res)
            eq_(len(mail.outbox), 0)


class TestPerms(mkt.site.tests.TestCase):
    fixtures = fixture('user_admin', 'group_admin', 'user_admin_group',
                       'user_999')

    def test_admin_user(self):
        # Admin should see views with Django's perm decorator and our own.
        self.login('admin@mozilla.com')
        eq_(self.client.get(reverse('zadmin.index')).status_code, 200)
        eq_(self.client.get(reverse('zadmin.settings')).status_code, 200)

    def test_staff_user(self):
        # Staff users have some privileges.
        user = UserProfile.objects.get(email='regular@mozilla.com')
        group = Group.objects.create(name='Staff', rules='AdminTools:View')
        GroupUser.objects.create(group=group, user=user)
        self.login('regular@mozilla.com')
        eq_(self.client.get(reverse('zadmin.index')).status_code, 200)
        eq_(self.client.get(reverse('zadmin.settings')).status_code, 200)

    def test_sr_reviewers_user(self):
        # Sr Reviewers users have only a few privileges.
        user = UserProfile.objects.get(email='regular@mozilla.com')
        group = Group.objects.create(name='Sr Reviewer',
                                     rules='ReviewerAdminTools:View')
        GroupUser.objects.create(group=group, user=user)
        self.login('regular@mozilla.com')
        eq_(self.client.get(reverse('zadmin.index')).status_code, 200)
        eq_(self.client.get(reverse('zadmin.settings')).status_code, 403)

    def test_unprivileged_user(self):
        # Unprivileged user.
        self.login('regular@mozilla.com')
        eq_(self.client.get(reverse('zadmin.index')).status_code, 403)
        eq_(self.client.get(reverse('zadmin.settings')).status_code, 403)
        # Anonymous users should also get a 403.
        self.client.logout()
        self.assert3xx(
            self.client.get(reverse('zadmin.index')),
            reverse('users.login') + '?to=/admin/')


class TestHome(mkt.site.tests.TestCase):
    fixtures = fixture('user_admin', 'group_admin', 'user_admin_group')

    def setUp(self):
        self.login('admin@mozilla.com')

    def test_home(self):
        # Test that the admin home page (which is AMO) can still be loaded
        # from Marketplace without exceptions.
        res = self.client.get(reverse('zadmin.index'))
        eq_(res.status_code, 200)


class TestGenerateError(mkt.site.tests.TestCase):
    fixtures = fixture('user_admin', 'group_admin', 'user_admin_group')

    def setUp(self):
        self.login('admin@mozilla.com')
        heka = settings.HEKA
        HEKA_CONF = {
            'logger': 'zamboni',
            'plugins': {'cef': ('heka_cef.cef_plugin:config_plugin',
                                {'override': True})},
            'stream': {'class': 'heka.streams.DebugCaptureStream'},
            'encoder': 'heka.encoders.NullEncoder',
        }
        from heka.config import client_from_dict_config
        self.heka = client_from_dict_config(HEKA_CONF, heka)
        self.heka.stream.msgs.clear()

    def test_heka_statsd(self):
        self.url = reverse('zadmin.generate-error')
        self.client.post(self.url,
                         {'error': 'heka_statsd'})

        eq_(len(self.heka.stream.msgs), 1)
        msg = self.heka.stream.msgs[0]

        eq_(msg.severity, 6)
        eq_(msg.logger, 'zamboni')
        eq_(msg.payload, '1')
        eq_(msg.type, 'counter')

        rate = [f for f in msg.fields if f.name == 'rate'][0]
        name = [f for f in msg.fields if f.name == 'name'][0]

        eq_(rate.value_double, [1.0])
        eq_(name.value_string, ['z.zadmin'])

    def test_heka_json(self):
        self.url = reverse('zadmin.generate-error')
        self.client.post(self.url,
                         {'error': 'heka_json'})

        eq_(len(self.heka.stream.msgs), 1)
        msg = self.heka.stream.msgs[0]

        eq_(msg.type, 'heka_json')
        eq_(msg.logger, 'zamboni')

        foo = [f for f in msg.fields if f.name == 'foo'][0]
        secret = [f for f in msg.fields if f.name == 'secret'][0]

        eq_(foo.value_string, ['bar'])
        eq_(secret.value_integer, [42])

    def test_heka_cef(self):
        self.url = reverse('zadmin.generate-error')
        self.client.post(self.url,
                         {'error': 'heka_cef'})

        eq_(len(self.heka.stream.msgs), 1)

        msg = self.heka.stream.msgs[0]

        eq_(msg.type, 'cef')
        eq_(msg.logger, 'zamboni')


class TestManifestRevalidation(mkt.site.tests.TestCase):
    fixtures = fixture('user_admin', 'group_admin', 'user_admin_group',
                       'webapp_337141', 'user_999')

    def setUp(self):
        self.url = reverse('zadmin.manifest_revalidation')

    def _test_revalidation(self):
        current_count = RereviewQueue.objects.count()
        response = self.client.post(self.url)
        eq_(response.status_code, 200)
        self.assertTrue('Manifest revalidation queued' in response.content)
        eq_(len(RereviewQueue.objects.all()), current_count + 1)

    def test_revalidation_by_reviewers(self):
        # Sr Reviewers users should be able to use the feature.
        user = UserProfile.objects.get(email='regular@mozilla.com')
        self.grant_permission(user, 'ReviewerAdminTools:View')
        self.login('regular@mozilla.com')

        self._test_revalidation()

    def test_revalidation_by_admin(self):
        # Admin users should be able to use the feature.
        self.login('admin@mozilla.com')
        self._test_revalidation()

    def test_unpriviliged_user(self):
        # Unprivileged user should not be able to reach the feature.
        self.login('regular@mozilla.com')
        eq_(self.client.post(self.url).status_code, 403)
