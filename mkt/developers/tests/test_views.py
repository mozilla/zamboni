# -*- coding: utf-8 -*-
import datetime
import json
import os
import tempfile
from contextlib import contextmanager
from uuid import UUID, uuid4

from django.conf import settings
from django.contrib.messages.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.urlresolvers import reverse
from django.test.client import RequestFactory
from django.test.utils import override_settings
from django.utils.encoding import smart_unicode

import mock
from jingo.helpers import urlparams
from jinja2.utils import escape
from nose.plugins.attrib import attr
from nose.tools import eq_, ok_
from pyquery import PyQuery as pq

import mkt
import mkt.site.tests
from lib.iarc.utils import get_iarc_app_title
from lib.iarc_v2.client import IARCException
from mkt.constants import MAX_PACKAGED_APP_SIZE
from mkt.developers import tasks
from mkt.developers.models import IARCRequest
from mkt.developers.views import (_filter_transactions, _get_transactions,
                                  _ratings_success_msg, _submission_msgs,
                                  content_ratings, content_ratings_edit)
from mkt.files.models import File, FileUpload
from mkt.files.tests.test_models import UploadTest as BaseUploadTest
from mkt.prices.models import AddonPremium, Price
from mkt.purchase.models import Contribution
from mkt.site.fixtures import fixture
from mkt.site.helpers import absolutify
from mkt.site.storage_utils import private_storage
from mkt.site.tests import assert_no_validation_errors
from mkt.site.tests.test_utils_ import get_image_path
from mkt.site.utils import app_factory, version_factory
from mkt.submit.models import AppSubmissionChecklist
from mkt.translations.models import Translation
from mkt.users.models import UserProfile
from mkt.versions.models import Version
from mkt.webapps.models import AddonDeviceType, AddonUpsell, AddonUser, Webapp
from mkt.zadmin.models import get_config, set_config


class AppHubTest(mkt.site.tests.TestCase):
    fixtures = fixture('prices', 'webapp_337141')

    def setUp(self):
        self.url = reverse('mkt.developers.apps')
        self.user = UserProfile.objects.get(email='steamcube@mozilla.com')
        self.login(self.user.email)

    def clone_addon(self, num, addon_id=337141):
        ids = []
        for i in xrange(num):
            addon = Webapp.objects.get(id=addon_id)
            new_addon = Webapp.objects.create(
                status=addon.status, name='cloned-addon-%s-%s' % (addon_id, i))
            AddonUser.objects.create(user=self.user, addon=new_addon)
            ids.append(new_addon.id)
        return ids

    def get_app(self):
        return Webapp.objects.get(id=337141)


class TestHome(mkt.site.tests.TestCase):
    fixtures = fixture('user_999')

    def setUp(self):
        self.url = reverse('mkt.developers.apps')

    def test_login_redirect(self):
        r = self.client.get(self.url)
        self.assertLoginRedirects(r, '/developers/submissions', 302)

    def test_home_anonymous(self):
        r = self.client.get(self.url, follow=True)
        eq_(r.status_code, 200)
        self.assertTemplateUsed(r, 'developers/login.html')

    def test_home_authenticated(self):
        self.login('regular@mozilla.com')
        r = self.client.get(self.url, follow=True)
        eq_(r.status_code, 200)
        self.assertTemplateUsed(r, 'developers/apps/dashboard.html')


class TestAppBreadcrumbs(AppHubTest):

    def setUp(self):
        super(TestAppBreadcrumbs, self).setUp()

    def test_regular_breadcrumbs(self):
        r = self.client.get(reverse('submit.app'), follow=True)
        eq_(r.status_code, 200)
        expected = [
            ('Home', reverse('home')),
            ('Developers', reverse('ecosystem.landing')),
            ('Submit App', None),
        ]
        mkt.site.tests.check_links(expected, pq(r.content)('#breadcrumbs li'))

    def test_webapp_management_breadcrumbs(self):
        webapp = Webapp.objects.get(id=337141)
        r = self.client.get(webapp.get_dev_url('edit'))
        eq_(r.status_code, 200)
        expected = [
            ('Home', reverse('home')),
            ('Developers', reverse('ecosystem.landing')),
            ('My Submissions', reverse('mkt.developers.apps')),
            (unicode(webapp.name), None),
        ]
        mkt.site.tests.check_links(expected, pq(r.content)('#breadcrumbs li'))


class TestAppDashboard(AppHubTest):

    def test_no_apps(self):
        Webapp.objects.all().delete()
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        eq_(pq(r.content)('#dashboard .item').length, 0)

    def test_public_app(self):
        app = self.get_app()
        doc = pq(self.client.get(self.url).content)
        item = doc('.item[data-addonid="%s"]' % app.id)
        assert item.find('.price'), 'Expected price'
        assert item.find('.item-details'), 'Expected item details'
        assert not item.find('p.incomplete'), (
            'Unexpected message about incomplete add-on')
        eq_(doc('.status-link').length, 1)
        eq_(doc('.more-actions-popup').length, 0)

    def test_incomplete_app(self):
        app = self.get_app()
        app.update(status=mkt.STATUS_NULL)
        doc = pq(self.client.get(self.url).content)
        assert doc('.item[data-addonid="%s"] p.incomplete' % app.id), (
            'Expected message about incompleted add-on')
        eq_(doc('.more-actions-popup').length, 0)

    def test_packaged_version(self):
        app = self.get_app()
        version = Version.objects.create(addon=app, version='1.23')
        app.update(_current_version=version, is_packaged=True)
        doc = pq(self.client.get(self.url).content)
        eq_(doc('.item[data-addonid="%s"] .item-current-version' % app.id
                ).text(),
            'Packaged App Version: 1.23')

    @mock.patch('mkt.webapps.tasks.update_cached_manifests')
    def test_pending_version(self, ucm):
        ucm.return_value = True

        app = self.get_app()
        app.update(is_packaged=True)
        Version.objects.create(addon=app, version='1.24')
        doc = pq(self.client.get(self.url).content)
        eq_(doc('.item[data-addonid="%s"] .item-latest-version' % app.id
                ).text(),
            'Pending Version: 1.24')

    def test_action_links(self):
        self.create_switch('view-transactions')
        app = self.get_app()
        app.update(public_stats=True, is_packaged=True,
                   premium_type=mkt.ADDON_PREMIUM_INAPP)
        doc = pq(self.client.get(self.url).content)
        expected = [
            ('Edit Listing', app.get_dev_url()),
            ('Add New Version', app.get_dev_url('versions')),
            ('Status & Versions', app.get_dev_url('versions')),
            ('Content Ratings', app.get_dev_url('ratings')),
            ('Compatibility & Payments', app.get_dev_url('payments')),
            ('In-App Payments', app.get_dev_url('in_app_payments')),
            ('Team Members', app.get_dev_url('owner')),
            ('View Listing', app.get_url_path()),

            ('Messages', app.get_comm_thread_url()),
            ('Statistics', app.get_stats_url()),
            ('Transactions', urlparams(
                reverse('mkt.developers.transactions'), app=app.id)),
        ]
        mkt.site.tests.check_links(
            expected, doc('a.action-link'), verify=False)

    def test_xss(self):
        app = self.get_app()
        app.name = u'My app é <script>alert(5)</script>'
        app.save()
        content = smart_unicode(self.client.get(self.url).content)
        ok_(not unicode(app.name) in content)
        ok_(unicode(escape(app.name)) in content)


class TestAppDashboardSorting(AppHubTest):

    def setUp(self):
        super(TestAppDashboardSorting, self).setUp()
        self.my_apps = self.user.addons
        self.url = reverse('mkt.developers.apps')
        self.clone(3)

    def clone(self, num=3):
        for x in xrange(num):
            app = app_factory()
            AddonUser.objects.create(addon=app, user=self.user)

    def test_pagination(self):
        doc = pq(self.client.get(self.url).content)('#dashboard')
        eq_(doc('.item').length, 4)
        eq_(doc('#sorter').length, 1)
        eq_(doc('.paginator').length, 0)

        self.clone(7)  # 4 + 7 = 11 (paginator appears for 11+ results)
        doc = pq(self.client.get(self.url).content)('#dashboard')
        eq_(doc('.item').length, 10)
        eq_(doc('#sorter').length, 1)
        eq_(doc('.paginator').length, 1)

        doc = pq(self.client.get(self.url, dict(page=2)).content)('#dashboard')
        eq_(doc('.item').length, 1)
        eq_(doc('#sorter').length, 1)
        eq_(doc('.paginator').length, 1)

    def _test_listing_sort(self, sort, key=None, reverse=True,
                           sel_class='opt'):
        r = self.client.get(self.url, dict(sort=sort))
        eq_(r.status_code, 200)
        sel = pq(r.content)('#sorter ul > li.selected')
        eq_(sel.find('a').attr('class'), sel_class)
        eq_(r.context['sorting'], sort)
        a = list(r.context['addons'].object_list)
        if key:
            eq_(a, sorted(a, key=lambda x: getattr(x, key), reverse=reverse))
        return a

    def test_default_sort(self):
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        eq_(r.context['sorting'], 'name')

        r = self.client.get(self.url, dict(name='xxx'))
        eq_(r.status_code, 200)
        eq_(r.context['sorting'], 'name')
        self._test_listing_sort('name', 'name', False)

    def test_newest_sort(self):
        self._test_listing_sort('created', 'created')


class TestDevRequired(AppHubTest):
    fixtures = fixture('webapp_337141', 'user_admin', 'user_admin_group',
                       'group_admin')

    def setUp(self):
        self.webapp = Webapp.objects.get(id=337141)
        self.get_url = self.webapp.get_dev_url('payments')
        self.post_url = self.webapp.get_dev_url('payments.disable')
        self.user = UserProfile.objects.get(email='steamcube@mozilla.com')
        self.login(self.user.email)
        self.au = AddonUser.objects.get(user=self.user, addon=self.webapp)
        eq_(self.au.role, mkt.AUTHOR_ROLE_OWNER)
        self.make_price()

    def test_anon(self):
        self.client.logout()
        r = self.client.get(self.get_url, follow=True)
        login = reverse('users.login')
        self.assert3xx(r, '%s?to=%s' % (login, self.get_url))

    def test_dev_get(self):
        eq_(self.client.get(self.get_url).status_code, 200)

    def test_dev_post(self):
        self.assert3xx(self.client.post(self.post_url), self.get_url)

    def test_viewer_get(self):
        self.au.role = mkt.AUTHOR_ROLE_VIEWER
        self.au.save()
        eq_(self.client.get(self.get_url).status_code, 200)

    def test_viewer_post(self):
        self.au.role = mkt.AUTHOR_ROLE_VIEWER
        self.au.save()
        eq_(self.client.post(self.get_url).status_code, 403)

    def test_disabled_post_dev(self):
        self.webapp.update(status=mkt.STATUS_DISABLED)
        eq_(self.client.post(self.get_url).status_code, 403)

    def test_disabled_post_admin(self):
        self.webapp.update(status=mkt.STATUS_DISABLED)
        self.login('admin@mozilla.com')
        self.assert3xx(self.client.post(self.post_url), self.get_url)


@mock.patch('mkt.developers.forms_payments.PremiumForm.clean',
            new=lambda x: x.cleaned_data)
class TestMarketplace(mkt.site.tests.TestCase):
    fixtures = fixture('prices', 'webapp_337141')

    def setUp(self):
        self.addon = Webapp.objects.get(id=337141)
        self.addon.update(status=mkt.STATUS_PUBLIC,
                          highest_status=mkt.STATUS_PUBLIC)

        self.url = self.addon.get_dev_url('payments')
        self.login('steamcube@mozilla.com')

    def get_price_regions(self, price):
        return sorted(set([p['region'] for p in price.prices() if p['paid']]))

    def setup_premium(self):
        self.price = Price.objects.get(pk=1)
        self.price_two = Price.objects.get(pk=3)
        self.other_addon = Webapp.objects.create(premium_type=mkt.ADDON_FREE)
        self.other_addon.update(status=mkt.STATUS_PUBLIC)
        AddonUser.objects.create(addon=self.other_addon,
                                 user=self.addon.authors.all()[0])
        AddonPremium.objects.create(addon=self.addon, price_id=self.price.pk)
        self.addon.update(premium_type=mkt.ADDON_PREMIUM)
        self.paid_regions = self.get_price_regions(self.price)
        self.paid_regions_two = self.get_price_regions(self.price_two)

    def get_data(self, **kw):
        data = {
            'form-TOTAL_FORMS': 0,
            'form-INITIAL_FORMS': 0,
            'form-MAX_NUM_FORMS': 0,
            'price': self.price.pk,
            'upsell_of': self.other_addon.pk,
            'regions': mkt.regions.REGION_IDS,
        }
        data.update(kw)
        return data

    def test_initial_free(self):
        AddonDeviceType.objects.create(
            addon=self.addon, device_type=mkt.DEVICE_GAIA.id)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        assert 'Change to Paid' in res.content

    def test_initial_paid(self):
        self.setup_premium()
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        eq_(res.context['form'].initial['price'], self.price.pk)
        assert 'Change to Free' in res.content

    def test_set(self):
        self.setup_premium()
        res = self.client.post(
            self.url, data=self.get_data(price=self.price_two.pk,
                                         regions=self.paid_regions_two))
        eq_(res.status_code, 302)
        self.addon = Webapp.objects.get(pk=self.addon.pk)
        eq_(self.addon.addonpremium.price, self.price_two)

    def test_set_upsell(self):
        self.setup_premium()
        res = self.client.post(self.url,
                               data=self.get_data(regions=self.paid_regions))
        eq_(res.status_code, 302)
        eq_(len(self.addon._upsell_to.all()), 1)

    def test_remove_upsell(self):
        self.setup_premium()
        upsell = AddonUpsell.objects.create(
            free=self.other_addon, premium=self.addon)
        eq_(self.addon._upsell_to.all()[0], upsell)
        self.client.post(self.url,
                         data=self.get_data(upsell_of='',
                                            regions=self.paid_regions))
        eq_(len(self.addon._upsell_to.all()), 0)

    def test_replace_upsell(self):
        self.setup_premium()
        # Make this add-on an upsell of some free add-on.
        upsell = AddonUpsell.objects.create(free=self.other_addon,
                                            premium=self.addon)
        # And this will become our new upsell, replacing the one above.
        new = Webapp.objects.create(premium_type=mkt.ADDON_FREE,
                                    status=mkt.STATUS_PUBLIC)
        AddonUser.objects.create(addon=new, user=self.addon.authors.all()[0])

        eq_(self.addon._upsell_to.all()[0], upsell)
        self.client.post(self.url, self.get_data(upsell_of=new.id,
                                                 regions=self.paid_regions))
        upsell = self.addon._upsell_to.all()
        eq_(len(upsell), 1)
        eq_(upsell[0].free, new)


class TestPubliciseVersion(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        self.app = self.get_webapp()
        self.app.update(is_packaged=True)
        self.url = self.app.get_dev_url('versions.publicise')
        self.status_url = self.app.get_dev_url('versions')
        self.login('steamcube@mozilla.com')

    def get_webapp(self):
        return Webapp.objects.get(pk=337141)

    def get_latest_version_status(self):
        v = Version.objects.get(pk=self.app.latest_version.pk)
        return v.all_files[0].status

    def post(self, pk=None):
        if not pk:
            pk = self.app.latest_version.pk
        return self.client.post(self.url, data={
            'version_id': pk
        })

    def test_logout(self):
        File.objects.filter(version__addon=self.app).update(
            status=mkt.STATUS_APPROVED)
        self.client.logout()
        res = self.post()
        eq_(res.status_code, 302)
        eq_(self.get_latest_version_status(), mkt.STATUS_APPROVED)

    def test_publicise_get(self):
        eq_(self.client.get(self.url).status_code, 405)

    @mock.patch('mkt.webapps.tasks.index_webapps')
    @mock.patch('mkt.webapps.tasks.update_cached_manifests')
    @mock.patch('mkt.webapps.models.Webapp.update_supported_locales')
    @mock.patch('mkt.webapps.models.Webapp.update_name_from_package_manifest')
    def test_publicise_version_new_approved(self, update_name, update_locales,
                                            update_cached_manifests,
                                            index_webapps):
        """ Test publishing the latest, approved version when the app is
        already public, with a current version also already public. """
        eq_(self.app.status, mkt.STATUS_PUBLIC)
        ver = version_factory(addon=self.app, version='2.0',
                              file_kw=dict(status=mkt.STATUS_APPROVED))
        eq_(self.app.latest_version, ver)
        ok_(self.app.current_version != ver)

        index_webapps.delay.reset_mock()
        eq_(update_name.call_count, 0)
        eq_(update_locales.call_count, 0)
        eq_(update_cached_manifests.delay.call_count, 0)

        res = self.post()
        eq_(res.status_code, 302)
        eq_(ver.reload().all_files[0].status, mkt.STATUS_PUBLIC)
        eq_(self.get_webapp().current_version, ver)

        eq_(update_name.call_count, 1)
        eq_(update_locales.call_count, 1)
        eq_(update_cached_manifests.delay.call_count, 1)

    @mock.patch('mkt.webapps.tasks.index_webapps')
    @mock.patch('mkt.webapps.tasks.update_cached_manifests')
    @mock.patch('mkt.webapps.models.Webapp.update_supported_locales')
    @mock.patch('mkt.webapps.models.Webapp.update_name_from_package_manifest')
    def test_publicise_version_new_unlisted(
            self, update_name, update_locales, update_cached_manifests,
            index_webapps):
        """ Test publishing the latest, approved version when the app is
        unlisted, with a current version also already public. """
        self.app.update(status=mkt.STATUS_UNLISTED)
        ver = version_factory(addon=self.app, version='2.0',
                              file_kw=dict(status=mkt.STATUS_APPROVED))
        eq_(self.app.latest_version, ver)
        ok_(self.app.current_version != ver)

        index_webapps.delay.reset_mock()
        eq_(update_name.call_count, 0)
        eq_(update_locales.call_count, 0)
        eq_(update_cached_manifests.delay.call_count, 0)

        res = self.post()
        eq_(res.status_code, 302)
        eq_(ver.reload().all_files[0].status, mkt.STATUS_PUBLIC)
        eq_(self.get_webapp().current_version, ver)

        eq_(update_name.call_count, 1)
        eq_(update_locales.call_count, 1)
        eq_(update_cached_manifests.delay.call_count, 1)

    @mock.patch('mkt.webapps.tasks.index_webapps')
    @mock.patch('mkt.webapps.tasks.update_cached_manifests')
    @mock.patch('mkt.webapps.models.Webapp.update_supported_locales')
    @mock.patch('mkt.webapps.models.Webapp.update_name_from_package_manifest')
    def test_publicise_version_cur_approved_app_public(
            self, update_name, update_locales, update_cached_manifests,
            index_webapps):
        """ Test publishing when the app is in a weird state: public but with
        only one version, which is approved. """
        self.app.latest_version.all_files[0].update(status=mkt.STATUS_APPROVED,
                                                    _signal=False)
        eq_(self.app.current_version, self.app.latest_version)
        eq_(self.app.status, mkt.STATUS_PUBLIC)

        index_webapps.delay.reset_mock()
        update_cached_manifests.delay.reset_mock()
        eq_(update_name.call_count, 0)
        eq_(update_locales.call_count, 0)
        eq_(update_cached_manifests.delay.call_count, 0)

        res = self.post()
        eq_(res.status_code, 302)
        eq_(self.app.current_version, self.app.latest_version)
        eq_(self.get_latest_version_status(), mkt.STATUS_PUBLIC)
        eq_(self.app.reload().status, mkt.STATUS_PUBLIC)

        eq_(update_name.call_count, 1)
        eq_(update_locales.call_count, 1)
        # Only one version, update_version() won't change it, the mini-manifest
        # doesn't need to be updated.
        eq_(update_cached_manifests.delay.call_count, 0)

    @mock.patch('mkt.webapps.tasks.index_webapps')
    @mock.patch('mkt.webapps.tasks.update_cached_manifests')
    @mock.patch('mkt.webapps.models.Webapp.update_supported_locales')
    @mock.patch('mkt.webapps.models.Webapp.update_name_from_package_manifest')
    def test_publicise_version_cur_approved(self, update_name, update_locales,
                                            update_cached_manifests,
                                            index_webapps):
        """ Test publishing when the only version of the app is approved
        doesn't change the app status. """
        self.app.update(status=mkt.STATUS_APPROVED)
        File.objects.filter(version__addon=self.app).update(
            status=mkt.STATUS_APPROVED)
        eq_(self.app.current_version, self.app.latest_version)

        index_webapps.delay.reset_mock()
        eq_(update_name.call_count, 0)
        eq_(update_locales.call_count, 0)
        eq_(update_cached_manifests.delay.call_count, 0)

        res = self.post()
        eq_(res.status_code, 302)
        eq_(self.app.current_version, self.app.latest_version)
        eq_(self.get_latest_version_status(), mkt.STATUS_PUBLIC)
        eq_(self.app.reload().status, mkt.STATUS_APPROVED)

        eq_(update_name.call_count, 1)
        eq_(update_locales.call_count, 1)
        eq_(update_cached_manifests.delay.call_count, 0)

    @mock.patch('mkt.webapps.tasks.index_webapps')
    @mock.patch('mkt.webapps.tasks.update_cached_manifests')
    @mock.patch('mkt.webapps.models.Webapp.update_supported_locales')
    @mock.patch('mkt.webapps.models.Webapp.update_name_from_package_manifest')
    def test_publicise_version_cur_unlisted(self, update_name, update_locales,
                                            update_cached_manifests,
                                            index_webapps):
        """ Test publishing a version of an unlisted app when the only
        version of the app is approved. """
        self.app.update(status=mkt.STATUS_UNLISTED, _current_version=None)
        File.objects.filter(version__addon=self.app).update(
            status=mkt.STATUS_APPROVED)

        index_webapps.delay.reset_mock()
        eq_(update_name.call_count, 0)
        eq_(update_locales.call_count, 0)
        eq_(update_cached_manifests.delay.call_count, 0)

        res = self.post()
        eq_(res.status_code, 302)
        app = self.app.reload()
        eq_(app.current_version, self.app.latest_version)
        eq_(self.get_latest_version_status(), mkt.STATUS_PUBLIC)
        eq_(app.status, mkt.STATUS_UNLISTED)

        eq_(update_name.call_count, 1)
        eq_(update_locales.call_count, 1)
        eq_(update_cached_manifests.delay.call_count, 1)

    @mock.patch('mkt.webapps.tasks.index_webapps')
    @mock.patch('mkt.webapps.tasks.update_cached_manifests')
    @mock.patch('mkt.webapps.models.Webapp.update_supported_locales')
    @mock.patch('mkt.webapps.models.Webapp.update_name_from_package_manifest')
    def test_publicise_version_pending(self, update_name, update_locales,
                                       update_cached_manifests, index_webapps):
        """ Test publishing a pending version isn't allowed. """
        ver = version_factory(addon=self.app, version='2.0',
                              file_kw=dict(status=mkt.STATUS_PENDING))
        res = self.post()
        eq_(res.status_code, 302)
        eq_(self.get_latest_version_status(), mkt.STATUS_PENDING)
        assert self.app.current_version != ver
        assert not update_name.called
        assert not update_locales.called

    def test_status(self):
        File.objects.filter(version__addon=self.app).update(
            status=mkt.STATUS_APPROVED)
        res = self.client.get(self.status_url)
        eq_(res.status_code, 200)
        doc = pq(res.content)
        eq_(doc('#version-list form').attr('action'), self.url)


class TestStatus(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141', 'user_admin', 'user_admin_group',
                       'group_admin')

    def setUp(self):
        self.webapp = Webapp.objects.get(id=337141)
        self.file = self.webapp.versions.latest().all_files[0]
        self.file.update(status=mkt.STATUS_REJECTED)
        self.status_url = self.webapp.get_dev_url('versions')
        self.login('steamcube@mozilla.com')

    def test_status_when_packaged_public_dev(self):
        self.webapp.update(is_packaged=True)
        res = self.client.get(self.status_url)
        eq_(res.status_code, 200)
        doc = pq(res.content)
        eq_(doc('#disable-addon').length, 1)
        eq_(doc('#delete-addon').length, 1)
        eq_(doc('#blocklist-app').length, 0)

    def test_status_when_packaged_public_admin(self):
        self.login('admin@mozilla.com')
        self.webapp.update(is_packaged=True)
        res = self.client.get(self.status_url)
        eq_(res.status_code, 200)
        doc = pq(res.content)
        eq_(doc('#disable-addon').length, 1)
        eq_(doc('#delete-addon').length, 1)
        eq_(doc('#blocklist-app').length, 1)

    def test_status_when_packaged_rejected_dev(self):
        self.webapp.update(is_packaged=True, status=mkt.STATUS_REJECTED)
        res = self.client.get(self.status_url)
        eq_(res.status_code, 200)
        doc = pq(res.content)
        eq_(doc('#disable-addon').length, 1)
        eq_(doc('#delete-addon').length, 1)
        eq_(doc('#blocklist-app').length, 0)

    def test_status_when_packaged_rejected_admin(self):
        self.login('admin@mozilla.com')
        self.webapp.update(is_packaged=True, status=mkt.STATUS_REJECTED)
        res = self.client.get(self.status_url)
        eq_(res.status_code, 200)
        doc = pq(res.content)
        eq_(doc('#disable-addon').length, 1)
        eq_(doc('#delete-addon').length, 1)
        eq_(doc('#blocklist-app').length, 0)

    def test_xss(self):
        version = self.webapp.versions.latest()
        self.webapp.update(is_packaged=True, _current_version=version,
                           _latest_version=version)
        self.file.update(status=mkt.STATUS_PUBLIC)
        version.update(version='<script>alert("xss")</script>')
        res = self.client.get(self.status_url)
        eq_(res.status_code, 200)
        doc = pq(res.content)('#version-status')
        assert '&lt;script&gt;' in doc.html()
        assert '<script>' not in doc.html()


class TestResumeStep(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        self.webapp = self.get_addon()
        self.url = reverse('submit.app.resume', args=[self.webapp.app_slug])
        self.login('steamcube@mozilla.com')

    def get_addon(self):
        return Webapp.objects.get(pk=337141)

    def test_no_step_redirect(self):
        r = self.client.get(self.url, follow=True)
        self.assert3xx(r, self.webapp.get_dev_url('edit'), 302)

    def test_step_redirects(self):
        AppSubmissionChecklist.objects.create(addon=self.webapp,
                                              terms=True, manifest=True)
        r = self.client.get(self.url, follow=True)
        self.assert3xx(r, reverse('submit.app.details',
                                  args=[self.webapp.app_slug]))

    def test_no_resume_when_done(self):
        AppSubmissionChecklist.objects.create(addon=self.webapp,
                                              terms=True, manifest=True,
                                              details=True)
        r = self.client.get(self.webapp.get_dev_url('edit'), follow=True)
        eq_(r.status_code, 200)

    def test_resume_without_checklist(self):
        r = self.client.get(reverse('submit.app.details',
                                    args=[self.webapp.app_slug]))
        eq_(r.status_code, 200)


class TestUpload(BaseUploadTest):
    fixtures = fixture('user_999')

    def setUp(self):
        super(TestUpload, self).setUp()
        self.login('regular@mozilla.com')
        self.package = self.packaged_app_path('mozball.zip')
        self.url = reverse('mkt.developers.upload')

    def post(self):
        # Has to be a binary, non xpi file.
        data = open(self.package, 'rb')
        return self.client.post(self.url, {'upload': data})

    def test_login_required(self):
        self.client.logout()
        r = self.post()
        eq_(r.status_code, 302)

    def test_create_fileupload(self):
        self.post()
        upload = FileUpload.objects.get(name='mozball.zip')
        eq_(upload.name, 'mozball.zip')
        eq_(upload.user.pk, 999)
        data = open(self.package, 'rb').read()
        eq_(private_storage.open(upload.path).read(), data)

    def test_fileupload_user(self):
        self.login('regular@mozilla.com')
        self.post()
        user = UserProfile.objects.get(email='regular@mozilla.com')
        eq_(FileUpload.objects.get().user, user)

    def test_fileupload_ascii_post(self):
        path = self.packaged_app_path('mozball.zip')
        data = open(os.path.join(settings.ROOT, path))
        replaced = path.replace('o', u'ö')
        r = self.client.post(self.url, {'upload':
                                        SimpleUploadedFile(replaced,
                                                           data.read())})
        # If this is broken, we'll get a traceback.
        eq_(r.status_code, 302)

    @mock.patch('mkt.constants.MAX_PACKAGED_APP_SIZE', 1024)
    @mock.patch('mkt.developers.tasks.validator')
    def test_fileupload_too_big(self, validator):
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            name = tf.name
            tf.write('x' * (MAX_PACKAGED_APP_SIZE + 1))

        with open(name) as tf:
            r = self.client.post(self.url, {'upload': tf})

        os.unlink(name)

        assert not validator.called, 'Validator erroneously invoked'

        # Test that we get back a validation failure for the upload.
        upload = FileUpload.objects.get()
        r = self.client.get(reverse('mkt.developers.upload_detail',
                                    args=[upload.uuid, 'json']))

        eq_(r.status_code, 200)
        data = json.loads(r.content)
        assert 'validation' in data, data
        assert 'success' in data['validation'], data
        assert not data['validation']['success'], data['validation']

    @attr('validator')
    def test_fileupload_validation(self):
        self.post()
        fu = FileUpload.objects.get(name='mozball.zip')
        assert_no_validation_errors(fu)
        assert fu.validation
        validation = json.loads(fu.validation)

        eq_(validation['success'], False)
        eq_(validation['errors'], 0)

    def test_redirect(self):
        r = self.post()
        upload = FileUpload.objects.get()
        url = reverse('mkt.developers.upload_detail', args=[upload.pk, 'json'])
        self.assert3xx(r, url)


class TestStandaloneUpload(BaseUploadTest):
    fixtures = fixture('user_999')

    def setUp(self):
        super(TestStandaloneUpload, self).setUp()
        self.package = self.packaged_app_path('mozball.zip')
        self.hosted_url = reverse('mkt.developers.standalone_hosted_upload')
        self.packaged_url = reverse(
            'mkt.developers.standalone_packaged_upload')
        fetch_manifest_patcher = mock.patch(
            'mkt.developers.views.fetch_manifest')
        self.fetch_manifest = fetch_manifest_patcher.start()
        self.fetch_manifest.delay.return_value = '{}'
        self.addCleanup(fetch_manifest_patcher.stop)

    def post_packaged(self):
        # Has to be a binary, non xpi file.
        data = open(self.package, 'rb')
        return self.client.post(self.packaged_url, {'upload': data})

    def post_hosted(self):
        manifest_url = 'https://mozilla.org/manifest.webapp'
        return self.client.post(self.hosted_url, {'manifest': manifest_url})

    def test_create_packaged(self):
        self.post_packaged()
        upload = FileUpload.objects.get(name='mozball.zip')
        eq_(upload.name, 'mozball.zip')
        eq_(upload.user, None)
        data = open(self.package, 'rb').read()
        eq_(private_storage.open(upload.path).read(), data)

    def test_create_packaged_user(self):
        self.login('regular@mozilla.com')
        self.post_packaged()
        upload = FileUpload.objects.get(name='mozball.zip')
        eq_(upload.name, 'mozball.zip')
        eq_(upload.user.pk, 999)
        data = open(self.package, 'rb').read()
        eq_(private_storage.open(upload.path).read(), data)

    def test_create_hosted(self):
        response = self.post_hosted()
        pk = response['location'].split('/')[-1]
        upload = FileUpload.objects.get(pk=pk)
        eq_(upload.user, None)

    def test_create_hosted_user(self):
        self.login('regular@mozilla.com')
        response = self.post_hosted()
        pk = response['location'].split('/')[-1]
        upload = FileUpload.objects.get(pk=pk)
        eq_(upload.user.pk, 999)


class TestUploadDetail(BaseUploadTest):
    fixtures = fixture('user_999')

    def setUp(self):
        super(TestUploadDetail, self).setUp()
        self.login('regular@mozilla.com')

    def post(self):
        # Has to be a binary, non xpi file.
        data = open(get_image_path('animated.png'), 'rb')
        return self.client.post(reverse('mkt.developers.upload'),
                                {'upload': data})

    def validation_ok(self):
        return {
            'errors': 0,
            'success': True,
            'warnings': 0,
            'notices': 0,
            'message_tree': {},
            'messages': [],
            'rejected': False,
            'metadata': {}}

    def upload_file(self, name):
        with self.file(name) as f:
            r = self.client.post(reverse('mkt.developers.upload'),
                                 {'upload': f})
        eq_(r.status_code, 302)

    def file_content(self, name):
        with self.file(name) as fp:
            return fp.read()

    @contextmanager
    def file(self, name):
        fn = os.path.join(settings.ROOT, 'mkt', 'developers', 'tests',
                          'addons', name)
        with open(fn, 'rb') as fp:
            yield fp

    @attr('validator')
    def test_detail_json(self):
        self.post()

        upload = FileUpload.objects.get()
        r = self.client.get(reverse('mkt.developers.upload_detail',
                                    args=[upload.uuid, 'json']))
        eq_(r.status_code, 200)
        data = json.loads(r.content)
        assert_no_validation_errors(data)
        eq_(data['url'],
            reverse('mkt.developers.upload_detail', args=[upload.uuid,
                                                          'json']))
        eq_(data['full_report_url'],
            reverse('mkt.developers.upload_detail', args=[upload.uuid]))
        # We must have tiers
        assert len(data['validation']['messages'])
        msg = data['validation']['messages'][0]
        eq_(msg['tier'], 1)

    @mock.patch('mkt.developers.tasks.requests.get')
    @mock.patch('mkt.developers.tasks.run_validator')
    def test_detail_for_free_extension_webapp(self, validator_mock,
                                              requests_mock):
        content = self.file_content('mozball.owa')
        response_mock = mock.Mock(status_code=200)
        response_mock.iter_content.return_value = mock.Mock(
            next=lambda: content)
        response_mock.headers = {'content-type': self.content_type}
        yield response_mock
        requests_mock.return_value = response_mock

        validator_mock.return_value = json.dumps(self.validation_ok())
        self.upload_file('mozball.owa')
        upload = FileUpload.objects.get()
        tasks.fetch_manifest('http://xx.com/manifest.owa', upload.pk)

        r = self.client.get(reverse('mkt.developers.upload_detail',
                                    args=[upload.uuid, 'json']))
        data = json.loads(r.content)
        eq_(data['validation']['messages'], [])  # no errors
        assert_no_validation_errors(data)  # no exception
        eq_(r.status_code, 200)
        eq_(data['url'],
            reverse('mkt.developers.upload_detail', args=[upload.uuid,
                                                          'json']))
        eq_(data['full_report_url'],
            reverse('mkt.developers.upload_detail', args=[upload.uuid]))

    def test_detail_view(self):
        self.post()
        upload = FileUpload.objects.get(name='animated.png')
        r = self.client.get(reverse('mkt.developers.upload_detail',
                                    args=[upload.uuid]))
        eq_(r.status_code, 200)
        doc = pq(r.content)
        eq_(doc('header h1').text(), 'Validation Results for animated.png')
        suite = doc('#addon-validator-suite')
        eq_(suite.attr('data-validateurl'),
            reverse('mkt.developers.standalone_upload_detail',
                    args=['hosted', upload.uuid]))
        eq_(suite('#suite-results-tier-2').length, 1)

    @mock.patch('bleach.callbacks.nofollow', lambda attrs, new: attrs)
    def test_detail_view_linkification(self):
        uid = '9b1b3898db8a4d99a049829a46969ab4'
        upload = FileUpload.objects.create(
            name='something.zip',
            validation=json.dumps({
                u'ending_tier': 1,
                u'success': False,
                u'warnings': 0,
                u'errors': 1,
                u'notices': 0,
                u'feature_profile': [],
                u'messages': [
                    {
                        u'column': None,
                        u'context': [
                            u'',
                            u'<button on-click="{{ port.name }}">uh</button>',
                            u''
                        ],
                        u'description': [
                            u'http://www.firefox.com'
                            u'<script>alert("hi");</script>',
                        ],
                        u'file': u'index.html',
                        u'id': [u'csp', u'script_attribute'],
                        u'line': 1638,
                        u'message': u'CSP Violation Detected',
                        u'tier': 2,
                        u'type': u'error',
                        u'uid': uid,
                    },
                ],
                u'metadata': {'ran_js_tests': 'yes'},
                u'manifest': {},
                u'feature_usage': [],
                u'permissions': [],

            }),
        )
        r = self.client.get(reverse('mkt.developers.standalone_upload_detail',
                                    args=['packaged', upload.uuid]))
        eq_(r.status_code, 200)
        data = json.loads(r.content)
        message = data['validation']['messages'][0]
        description = message['description'][0]
        eq_(description,
            '<a href="http://www.firefox.com">http://www.firefox.com</a>'
            '&lt;script&gt;alert("hi");&lt;/script&gt;')
        context = message['context'][1]
        eq_(context,
            '&lt;button on-click=&#34;{{ port.name }}&#34;&gt;'
            'uh&lt;/button&gt;')


def assert_json_error(request, field, msg):
    eq_(request.status_code, 400)
    eq_(request['Content-Type'], 'application/json')
    field = '__all__' if field is None else field
    content = json.loads(request.content)
    assert field in content, '%r not in %r' % (field, content)
    eq_(content[field], [msg])


def assert_json_field(request, field, msg):
    eq_(request.status_code, 200)
    eq_(request['Content-Type'], 'application/json')
    content = json.loads(request.content)
    assert field in content, '%r not in %r' % (field, content)
    eq_(content[field], msg)


class TestDeleteApp(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141', 'user_admin', 'user_admin_group',
                       'group_admin')

    def setUp(self):
        self.webapp = Webapp.objects.get(id=337141)
        self.url = self.webapp.get_dev_url('delete')
        self.versions_url = self.webapp.get_dev_url('versions')
        self.dev_url = reverse('mkt.developers.apps')
        self.login('admin@mozilla.com')

    def test_delete_get(self):
        eq_(self.client.get(self.url).status_code, 405)

    def test_delete_nonincomplete(self):
        r = self.client.post(self.url)
        self.assert3xx(r, self.dev_url)
        eq_(Webapp.objects.count(), 0, 'App should have been deleted.')

    def test_delete_incomplete(self):
        self.webapp.update(status=mkt.STATUS_NULL)
        r = self.client.post(self.url)
        self.assert3xx(r, self.dev_url)
        eq_(Webapp.objects.count(), 0, 'App should have been deleted.')

    def test_delete_incomplete_manually(self):
        webapp = app_factory(name='Boop', status=mkt.STATUS_NULL)
        eq_(list(Webapp.objects.filter(id=webapp.id)), [webapp])
        webapp.delete('POOF!')
        eq_(list(Webapp.objects.filter(id=webapp.id)), [],
            'App should have been deleted.')

    def check_delete_redirect(self, src, dst):
        r = self.client.post(urlparams(self.url, to=src))
        self.assert3xx(r, dst)
        eq_(Webapp.objects.count(), 0, 'App should have been deleted.')

    def test_delete_redirect_to_dashboard(self):
        self.check_delete_redirect(self.dev_url, self.dev_url)

    def test_delete_redirect_to_dashboard_with_qs(self):
        url = self.dev_url + '?sort=created'
        self.check_delete_redirect(url, url)

    def test_form_action_on_status_page(self):
        # If we started on app's Manage Status page, upon deletion we should
        # be redirected to the Dashboard.
        r = self.client.get(self.versions_url)
        eq_(pq(r.content)('.modal-delete form').attr('action'), self.url)
        self.check_delete_redirect('', self.dev_url)

    def test_owner_deletes(self):
        self.login('steamcube@mozilla.com')
        r = self.client.post(self.url, follow=True)
        eq_(pq(r.content)('.notification-box').text(), 'App deleted.')
        with self.assertRaises(Webapp.DoesNotExist):
            Webapp.objects.get(pk=self.webapp.pk)


class TestEnableDisable(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141', 'user_2519')

    def setUp(self):
        self.webapp = Webapp.objects.get(id=337141)
        self.enable_url = self.webapp.get_dev_url('enable')
        self.disable_url = self.webapp.get_dev_url('disable')
        self.login('steamcube@mozilla.com')

    def test_get(self):
        eq_(self.client.get(self.enable_url).status_code, 405)
        eq_(self.client.get(self.disable_url).status_code, 405)

    def test_not_allowed(self):
        self.client.logout()
        self.assertLoginRequired(self.client.get(self.enable_url))
        self.assertLoginRequired(self.client.get(self.disable_url))

    def test_enable(self):
        self.webapp.update(disabled_by_user=True)
        self.client.post(self.enable_url)
        eq_(self.webapp.reload().disabled_by_user, False)

    def test_disable(self):
        self.client.post(self.disable_url)
        eq_(self.webapp.reload().disabled_by_user, True)

    def test_disable_deleted_versions(self):
        """
        Test when we ban an app with deleted versions we don't include
        the deleted version's files when calling `hide_disabled_file` or we'll
        cause server errors b/c we can't query the version.
        """
        self.webapp.update(is_packaged=True)
        self.webapp.latest_version.update(deleted=True)
        self.client.post(self.disable_url)
        eq_(self.webapp.reload().disabled_by_user, True)


class TestRemoveLocale(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        self.webapp = Webapp.objects.get(id=337141)
        self.url = self.webapp.get_dev_url('remove-locale')
        self.login('steamcube@mozilla.com')

    def test_bad_request(self):
        r = self.client.post(self.url)
        eq_(r.status_code, 400)

    def test_success(self):
        self.webapp.name = {'en-US': 'woo', 'es': 'ay', 'el': 'yeah'}
        self.webapp.save()
        self.webapp.remove_locale('el')
        r = self.client.post(self.url, {'locale': 'el'})
        eq_(r.status_code, 200)
        qs = list(Translation.objects.filter(localized_string__isnull=False)
                  .values_list('locale', flat=True)
                  .filter(id=self.webapp.name_id))
        eq_(qs, ['en-us', 'es'])

    def test_delete_default_locale(self):
        r = self.client.post(self.url, {'locale': self.webapp.default_locale})
        eq_(r.status_code, 400)


class TestTerms(mkt.site.tests.TestCase):
    fixtures = fixture('user_999')

    def setUp(self):
        self.user = self.get_user()
        self.login(self.user.email)
        self.url = reverse('mkt.developers.apps.terms')

    def get_user(self):
        return UserProfile.objects.get(email='regular@mozilla.com')

    def test_login_required(self):
        self.client.logout()
        self.assertLoginRequired(self.client.get(self.url))

    def test_accepted(self):
        self.user.update(read_dev_agreement=datetime.datetime.now())
        res = self.client.get(self.url)
        doc = pq(res.content)
        eq_(doc('#dev-agreement').length, 1)
        eq_(doc('#agreement-form').length, 0)

    def test_not_accepted(self):
        self.user.update(read_dev_agreement=None)
        res = self.client.get(self.url)
        doc = pq(res.content)
        eq_(doc('#dev-agreement').length, 1)
        eq_(doc('#agreement-form').length, 1)

    def test_accept(self):
        self.user.update(read_dev_agreement=None)
        res = self.client.post(self.url, {'read_dev_agreement': 'yeah'})
        eq_(res.status_code, 200)
        assert self.get_user().read_dev_agreement

    @mock.patch.object(settings, 'DEV_AGREEMENT_LAST_UPDATED',
                       mkt.site.tests.days_ago(-5).date())
    def test_update(self):
        past = self.days_ago(10)
        self.user.update(read_dev_agreement=past)
        res = self.client.post(self.url, {'read_dev_agreement': 'yeah'})
        eq_(res.status_code, 200)
        assert self.get_user().read_dev_agreement != past

    @mock.patch.object(settings, 'DEV_AGREEMENT_LAST_UPDATED',
                       mkt.site.tests.days_ago(-5).date())
    def test_past(self):
        past = self.days_ago(10)
        self.user.update(read_dev_agreement=past)
        res = self.client.get(self.url)
        doc = pq(res.content)
        eq_(doc('#site-notice').length, 1)
        eq_(doc('#dev-agreement').length, 1)
        eq_(doc('#agreement-form').length, 1)

    def test_not_past(self):
        res = self.client.get(self.url)
        doc = pq(res.content)
        eq_(doc('#site-notice').length, 0)
        eq_(doc('#dev-agreement').length, 1)
        eq_(doc('#agreement-form').length, 0)

    def test_l10n_good(self):
        for locale in ('en-US', 'es', 'pl'):
            res = self.client.get(self.url, {'lang': locale})
            eq_(res.status_code, 200)
            self.assertTemplateUsed(res, 'dev-agreement/%s.html' % locale)

    def test_l10n_fallback(self):
        res = self.client.get(self.url, {'lang': 'swag'})
        eq_(res.status_code, 200)
        self.assertTemplateUsed(res, 'dev-agreement/en-US.html')

    def test_redirect_to_relative(self):
        api_url = reverse('mkt.developers.apps.api')
        res = self.client.post(urlparams(self.url, to=api_url),
                               {'read_dev_agreement': 'yeah'})
        self.assert3xx(res, api_url)

    def test_redirect_to_external(self):
        res = self.client.post(urlparams(self.url, to='https://hy.fr'),
                               {'read_dev_agreement': 'yeah'})
        eq_(res.status_code, 200)


class TestTransactionList(mkt.site.tests.TestCase):
    fixtures = fixture('user_999')

    def setUp(self):
        """Create and set up apps for some filtering fun."""
        self.create_switch(name='view-transactions')
        self.url = reverse('mkt.developers.transactions')
        self.login('regular@mozilla.com')

        self.apps = [app_factory(), app_factory()]
        self.user = UserProfile.objects.get(id=999)
        for app in self.apps:
            AddonUser.objects.create(addon=app, user=self.user)

        # Set up transactions.
        tx0 = Contribution.objects.create(addon=self.apps[0],
                                          type=mkt.CONTRIB_PURCHASE,
                                          user=self.user,
                                          uuid=12345)
        tx1 = Contribution.objects.create(addon=self.apps[1],
                                          type=mkt.CONTRIB_REFUND,
                                          user=self.user,
                                          uuid=67890)
        tx0.update(created=datetime.date(2011, 12, 25))
        tx1.update(created=datetime.date(2012, 1, 1))
        self.txs = [tx0, tx1]

    def test_200(self):
        r = self.client.get(self.url)
        eq_(r.status_code, 200)

    def test_own_apps(self):
        """Only user's transactions are shown."""
        app_factory()
        r = RequestFactory().get(self.url)
        r.user = self.user
        transactions = _get_transactions(r)[1]
        self.assertSetEqual([tx.addon for tx in transactions], self.apps)

    def test_filter(self):
        """For each field in the form, run it through view and check results.
        """
        tx0 = self.txs[0]
        tx1 = self.txs[1]

        self.do_filter(self.txs)
        self.do_filter(self.txs, transaction_type='None', app='oshawott')

        self.do_filter([tx0], app=tx0.addon.id)
        self.do_filter([tx1], app=tx1.addon.id)

        self.do_filter([tx0], transaction_type=tx0.type)
        self.do_filter([tx1], transaction_type=tx1.type)

        self.do_filter([tx0], transaction_id=tx0.uuid)
        self.do_filter([tx1], transaction_id=tx1.uuid)

        self.do_filter(self.txs, date_from=datetime.date(2011, 12, 1))
        self.do_filter([tx1], date_from=datetime.date(2011, 12, 30),
                       date_to=datetime.date(2012, 2, 1))

    def do_filter(self, expected_txs, **kw):
        """Checks that filter returns the expected ids

        expected_ids -- list of app ids expected in the result.
        """
        qs = _filter_transactions(Contribution.objects.all(), kw)

        self.assertSetEqual(qs.values_list('id', flat=True),
                            [tx.id for tx in expected_txs])


class TestContentRatings(mkt.site.tests.TestCase):
    fixtures = fixture('user_admin', 'user_admin_group', 'group_admin')

    def setUp(self):
        self.app = app_factory()
        self.app.latest_version.update(
            _developer_name='Lex Luthor <lex@kryptonite.org>')
        self.user = UserProfile.objects.get()
        self.url = reverse('mkt.developers.apps.ratings',
                           args=[self.app.app_slug])
        self.req = mkt.site.tests.req_factory_factory(self.url, user=self.user)
        self.req.session = mock.MagicMock()

    @override_settings(IARC_SUBMISSION_ENDPOINT='https://yo.lo',
                       IARC_STOREFRONT_ID=1, IARC_PLATFORM='Firefox',
                       IARC_PASSWORD='s3kr3t')
    def test_edit(self):
        self.req._messages = default_storage(self.req)
        r = content_ratings_edit(self.req, app_slug=self.app.app_slug)
        doc = pq(r.content)

        # Check the form action.
        form = doc('#ratings-edit form')[0]
        eq_(form.action, 'https://yo.lo')

        # Check the hidden form values.
        values = dict(form.form_values())
        eq_(values['storefront'], '1')
        # Note: The HTML is actually double escaped but pyquery shows it how it
        # will be send to IARC, which is singly escaped.
        eq_(values['company'], 'Lex Luthor <lex@kryptonite.org>')
        eq_(values['email'], self.user.email)
        eq_(values['appname'], get_iarc_app_title(self.app))
        eq_(values['platform'], 'Firefox')
        eq_(values['token'], self.app.iarc_token())
        eq_(values['pingbackurl'],
            absolutify(reverse('content-ratings-pingback',
                               args=[self.app.app_slug])))

    def test_edit_default_locale(self):
        """Ensures the form uses the app's default locale."""
        self.req._messages = default_storage(self.req)
        self.app.name = {'es': u'Español', 'en-US': 'English'}
        self.app.default_locale = 'es'
        self.app.save()

        r = content_ratings_edit(self.req, app_slug=self.app.app_slug)
        doc = pq(r.content.decode('utf-8'))
        eq_(u'Español' in
            dict(doc('#ratings-edit form')[0].form_values())['appname'],
            True)

        self.app.update(default_locale='en-US')
        r = content_ratings_edit(self.req, app_slug=self.app.app_slug)
        doc = pq(r.content.decode('utf-8'))
        eq_(u'English' in
            dict(doc('#ratings-edit form')[0].form_values())['appname'],
            True)

    def test_summary(self):
        rbs = mkt.ratingsbodies
        ratings = {
            rbs.CLASSIND: rbs.CLASSIND_L,
            rbs.GENERIC: rbs.GENERIC_3,
            rbs.USK: rbs.USK_18,
            rbs.ESRB: rbs.ESRB_M,
            rbs.PEGI: rbs.PEGI_12
        }
        self.app.set_content_ratings(ratings)
        self.app.set_descriptors(['has_classind_sex', 'has_pegi_lang'])
        self.app.set_interactives(['has_users_interact'])

        r = content_ratings(self.req, app_slug=self.app.app_slug)
        doc = pq(r.content)

        self.assertSetEqual([name.text for name in doc('.name')],
                            [body.name for body in ratings])
        self.assertSetEqual([name.text.strip() for name in doc('.descriptor')],
                            ['Sexo'])
        self.assertSetEqual(
            [name.text.strip() for name in doc('.interactive')],
            ['Users Interact'])

    def test_edit_iarc_app_form(self):
        self.req._messages = default_storage(self.req)
        r = content_ratings_edit(self.req, app_slug=self.app.app_slug)
        doc = pq(r.content)
        assert not doc('#id_submission_id').attr('value')
        assert not doc('#id_security_code').attr('value')

        self.app.set_iarc_info(1234, 'abcd')
        r = content_ratings_edit(self.req, app_slug=self.app.app_slug)
        doc = pq(r.content)
        eq_(doc('#id_submission_id').attr('value'), '1234')
        eq_(doc('#id_security_code').attr('value'), 'abcd')


class TestContentRatingsV2(mkt.site.tests.TestCase):
    fixtures = fixture('user_admin', 'user_admin_group', 'group_admin')

    def setUp(self):
        self.app = app_factory()
        self.app.latest_version.update(
            _developer_name='Lex Luthor <lex@kryptonite.org>')
        self.user = UserProfile.objects.get()
        self.url = reverse('mkt.developers.apps.ratings',
                           args=[self.app.app_slug])
        self.req = mkt.site.tests.req_factory_factory(self.url, user=self.user)
        self.req.session = mock.MagicMock()
        self.create_switch('iarc-upgrade-v2')

    @override_settings(IARC_V2_SUBMISSION_ENDPOINT='https://yo.lo',
                       IARC_V2_STORE_ID='abc', IARC_PLATFORM='Firefox')
    def test_edit_form(self):
        self.req._messages = default_storage(self.req)
        r = content_ratings_edit(self.req, app_slug=self.app.app_slug)
        doc = pq(r.content)

        # Check the form action.
        form = doc('#ratings-edit form')[0]
        eq_(form.action, 'https://yo.lo')

        # Check the hidden form values.
        values = dict(form.form_values())
        eq_(values['StoreID'], 'abc')

    def test_creates_store_request_id(self):
        self.req._messages = default_storage(self.req)
        with self.assertRaises(IARCRequest.DoesNotExist):
            self.app.iarc_request

        r = content_ratings_edit(self.req, app_slug=self.app.app_slug)
        doc = pq(r.content)

        # Check the form action.
        form = doc('#ratings-edit form')[0]
        values = dict(form.form_values())
        eq_(values['StoreRequestID'],
            unicode(UUID(IARCRequest.objects.get(app=self.app).uuid)))
        ok_(IARCRequest.objects.filter(
            uuid=UUID(values['StoreRequestID']).hex).exists())

    def test_uses_store_request_id(self):
        self.req._messages = default_storage(self.req)
        IARCRequest.objects.create(
            app=self.app, uuid=UUID('515d56bbaf074be58748f0c8728ddc1d'))

        r = content_ratings_edit(self.req, app_slug=self.app.app_slug)
        doc = pq(r.content)

        # Check the form action.
        form = doc('#ratings-edit form')[0]
        values = dict(form.form_values())
        eq_(values['StoreRequestID'], '515d56bb-af07-4be5-8748-f0c8728ddc1d')

    def test_existing_cert_form(self):
        response = content_ratings_edit(self.req, app_slug=self.app.app_slug)
        doc = pq(response.content)
        # V1 fields are not present, V1 is (and empty).
        ok_(not doc('#id_submission_id'))
        ok_(not doc('#id_security_code'))
        ok_(doc('#id_cert_id'))
        ok_(not doc('#id_cert_id').attr('value'))

        cert_id = unicode(uuid4())
        self.app.set_iarc_certificate(cert_id)
        response = content_ratings_edit(self.req, app_slug=self.app.app_slug)
        doc = pq(response.content)
        eq_(doc('#id_cert_id').attr('value'), cert_id)

    def test_existing_cert_form_submit_error(self):
        self.req.method = 'POST'
        self.req.POST = {
            'cert_id': 'lol'
        }
        response = content_ratings_edit(self.req, app_slug=self.app.app_slug)
        doc = pq(response.content)
        eq_(doc('.iarc-cert .errorlist').text(),
            'badly formed hexadecimal UUID string')

    @mock.patch('mkt.developers.forms.search_and_attach_cert')
    def test_existing_cert_form_submit_iarc_server_error(
            self, search_and_attach_cert_mock):
        search_and_attach_cert_mock.side_effect = IARCException
        cert_id = unicode(uuid4())
        self.app.set_iarc_certificate(cert_id)
        self.req.method = 'POST'
        self.req.POST = {
            'cert_id': cert_id
        }
        response = content_ratings_edit(self.req, app_slug=self.app.app_slug)
        doc = pq(response.content)
        ok_(doc('.iarc-cert .errorlist').text().startswith(
            'This Certificate ID is not recognized by IARC'))

    @mock.patch('mkt.developers.forms.search_and_attach_cert')
    def test_existing_cert_form_submit_success(
            self, search_and_attach_cert_mock):
        cert_id = unicode(uuid4())
        self.app.set_iarc_certificate(cert_id)
        self.req.method = 'POST'
        self.req.POST = {
            'cert_id': cert_id
        }
        self.req._messages = default_storage(self.req)
        response = content_ratings_edit(self.req, app_slug=self.app.app_slug)
        self.assert3xx(response, self.url, 302)
        eq_(search_and_attach_cert_mock.call_count, 1)
        eq_(search_and_attach_cert_mock.call_args[0], (self.app, cert_id))


class TestContentRatingsSuccessMsg(mkt.site.tests.TestCase):

    def setUp(self):
        self.app = app_factory(status=mkt.STATUS_NULL)

    def _make_complete(self, complete_errs):
        complete_errs.return_value = {}

    def _rate_app(self):
        self.app.content_ratings.create(ratings_body=0, rating=0)

    def test_create_rating_still_incomplete(self):
        self._rate_app()
        eq_(_ratings_success_msg(self.app, mkt.STATUS_NULL, None),
            _submission_msgs()['content_ratings_saved'])

    @mock.patch('mkt.webapps.models.Webapp.completion_errors')
    def test_create_rating_now_complete(self, complete_errs):
        self._rate_app()
        self.app.update(status=mkt.STATUS_PENDING)
        eq_(_ratings_success_msg(self.app, mkt.STATUS_NULL, None),
            _submission_msgs()['complete'])

    @mock.patch('mkt.webapps.models.Webapp.completion_errors')
    def test_create_rating_public_app(self, complete_errs):
        self._rate_app()
        self.app.update(status=mkt.STATUS_PUBLIC)
        eq_(_ratings_success_msg(self.app, mkt.STATUS_PUBLIC, None),
            _submission_msgs()['content_ratings_saved'])

    @mock.patch('mkt.webapps.models.Webapp.completion_errors')
    def test_update_rating_still_complete(self, complete_errs):
        self._rate_app()
        self.app.update(status=mkt.STATUS_PENDING)
        eq_(_ratings_success_msg(self.app, mkt.STATUS_PENDING,
                                 self.days_ago(5).isoformat()),
            _submission_msgs()['content_ratings_saved'])


class TestMessageOfTheDay(mkt.site.tests.TestCase):
    fixtures = fixture('user_editor', 'user_999')

    def setUp(self):
        self.login('editor')
        self.url = reverse('mkt.developers.motd')
        self.key = u'mkt_developers_motd'
        set_config(self.key, u'original value')

    def test_not_logged_in(self):
        self.client.logout()
        req = self.client.get(self.url, follow=True)
        self.assertLoginRedirects(req, self.url)

    def test_perms_not_editor(self):
        self.client.logout()
        self.login('regular@mozilla.com')
        eq_(self.client.get(self.url).status_code, 403)

    def test_perms_not_motd(self):
        # You can't see the edit page if you can't edit it.
        req = self.client.get(self.url)
        eq_(req.status_code, 403)

    def test_motd_form_initial(self):
        # Only users in the MOTD group can POST.
        user = UserProfile.objects.get(email='editor@mozilla.com')
        self.grant_permission(user, 'DeveloperMOTD:Edit')

        # Get is a 200 with a form.
        req = self.client.get(self.url)
        eq_(req.status_code, 200)
        eq_(req.context['form'].initial['motd'], u'original value')

    def test_motd_empty_post(self):
        # Only users in the MOTD group can POST.
        user = UserProfile.objects.get(email='editor@mozilla.com')
        self.grant_permission(user, 'DeveloperMOTD:Edit')

        # Empty post throws an error.
        req = self.client.post(self.url, dict(motd=''))
        eq_(req.status_code, 200)  # Didn't redirect after save.
        eq_(pq(req.content)('#editor-motd .errorlist').text(),
            'This field is required.')

    def test_motd_real_post(self):
        # Only users in the MOTD group can POST.
        user = UserProfile.objects.get(email='editor@mozilla.com')
        self.grant_permission(user, 'DeveloperMOTD:Edit')

        # A real post now.
        req = self.client.post(self.url, dict(motd='new motd'))
        self.assert3xx(req, self.url)
        eq_(get_config(self.key), u'new motd')
