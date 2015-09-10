# -*- coding: utf-8 -*-
import collections
import json
import uuid
from urlparse import urlparse

from django.conf import settings
from django.core import mail
from django.core.urlresolvers import reverse
from django.http import QueryDict
from django.utils.http import urlencode

from jingo.helpers import urlparams
from mock import patch, Mock
from nose.tools import eq_, ok_

import mkt
from mkt.account.views import MineMixin
from mkt.access.models import Group, GroupUser
from mkt.api.tests.test_oauth import RestOAuth
from mkt.constants.apps import INSTALL_TYPE_REVIEWER
from mkt.site.fixtures import fixture
from mkt.site.tests import TestCase
from mkt.site.utils import app_factory
from mkt.webapps.models import Installed, Webapp
from mkt.users.models import UserProfile


class TestPotatoCaptcha(object):

    def _test_bad_api_potato_data(self, response, data=None):
        if not data:
            data = json.loads(response.content)
        eq_(400, response.status_code)
        ok_('non_field_errors' in data)
        eq_(data['non_field_errors'], [u'Form could not be submitted.'])


class FakeResourceBase(object):
    pass


class FakeResource(MineMixin, FakeResourceBase):
    def __init__(self, pk, request):
        self.kwargs = {'pk': pk}
        self.request = request


class TestMine(TestCase):
    fixtures = fixture('user_2519')

    def setUp(self):
        self.request = Mock()
        self.request.user = UserProfile.objects.get(id=2519)

    @patch.object(FakeResourceBase, 'get_object', create=True)
    def test_get_object(self, mocked_get_object):
        r = FakeResource(999, self.request)
        r.get_object()
        eq_(r.kwargs['pk'], 999)

        r = FakeResource('mine', self.request)
        r.get_object()
        eq_(r.kwargs['pk'], 2519)


class TestPermission(RestOAuth):
    fixtures = fixture('user_2519', 'user_10482')

    def setUp(self):
        super(TestPermission, self).setUp()
        self.get_url = reverse('account-permissions', kwargs={'pk': 2519})
        self.user = UserProfile.objects.get(pk=2519)

    def test_has_cors(self):
        self.assertCORS(self.client.get(self.get_url), 'get')

    def test_verbs(self):
        self._allowed_verbs(self.get_url, ('get'))

    def test_other(self):
        self.get_url = reverse('account-permissions', kwargs={'pk': 10482})
        eq_(self.client.get(self.get_url).status_code, 403)

    def test_no_permissions(self):
        res = self.client.get(self.get_url)
        eq_(res.status_code, 200, res.content)
        self.assertSetEqual(
            ['admin', 'developer', 'localizer', 'lookup', 'curator',
             'reviewer', 'webpay', 'website_submitter', 'stats',
             'revenue_stats', 'content_tools_login',
             'content_tools_addon_submit', 'content_tools_addon_review'],
            res.json['permissions'].keys()
        )
        ok_(not all(res.json['permissions'].values()))

    def test_some_permission(self):
        self.grant_permission(self.user, 'Localizers:%')
        res = self.client.get(self.get_url)
        eq_(res.status_code, 200)
        ok_(res.json['permissions']['localizer'])

    def test_mine(self):
        self.get_url = reverse('account-permissions', kwargs={'pk': 'mine'})
        self.test_some_permission()

    def test_mine_anon(self):
        self.get_url = reverse('account-permissions', kwargs={'pk': 'mine'})
        res = self.anon.get(self.get_url)
        eq_(res.status_code, 403)

    def test_publisher(self):
        res = self.client.get(self.get_url)
        eq_(res.status_code, 200)
        ok_(not res.json['permissions']['curator'])

    def test_publisher_ok(self):
        self.grant_permission(self.user, 'Collections:Curate')
        res = self.client.get(self.get_url)
        eq_(res.status_code, 200)
        ok_(res.json['permissions']['curator'])

    def test_feed_publisher_ok(self):
        self.grant_permission(self.user, 'Feed:Curate')
        res = self.client.get(self.get_url)
        eq_(res.status_code, 200)
        ok_(res.json['permissions']['curator'])

    def test_webpay(self):
        res = self.client.get(self.get_url)
        eq_(res.status_code, 200)
        ok_(not res.json['permissions']['webpay'])

    def test_webpay_ok(self):
        self.grant_permission(self.user, 'ProductIcon:Create')
        self.grant_permission(self.user, 'Transaction:NotifyFailure')
        res = self.client.get(self.get_url)
        eq_(res.status_code, 200)
        ok_(res.json['permissions']['webpay'])

    def test_website_submitter(self):
        res = self.client.get(self.get_url)
        eq_(res.status_code, 200)
        ok_(not res.json['permissions']['website_submitter'])

    def test_website_submitter_ok(self):
        self.grant_permission(self.user, 'Websites:Submit')
        res = self.client.get(self.get_url)
        eq_(res.status_code, 200)
        ok_(res.json['permissions']['website_submitter'])

    def test_stats(self):
        res = self.client.get(self.get_url)
        eq_(res.status_code, 200)
        ok_(not res.json['permissions']['stats'])

    def test_stats_ok(self):
        self.grant_permission(self.user, 'Stats:View')
        res = self.client.get(self.get_url)
        eq_(res.status_code, 200)
        ok_(res.json['permissions']['stats'])

    def test_revenue_stats(self):
        res = self.client.get(self.get_url)
        eq_(res.status_code, 200)
        ok_(not res.json['permissions']['revenue_stats'])

    def test_revenue_stats_ok(self):
        self.grant_permission(self.user, 'RevenueStats:View')
        res = self.client.get(self.get_url)
        eq_(res.status_code, 200)
        ok_(res.json['permissions']['revenue_stats'])


class TestAccount(RestOAuth):
    fixtures = fixture('user_2519', 'user_10482', 'webapp_337141')

    def setUp(self):
        super(TestAccount, self).setUp()
        self.url = reverse('account-settings', kwargs={'pk': 2519})
        self.user = UserProfile.objects.get(pk=2519)

    def test_has_cors(self):
        self.assertCORS(self.client.get(self.url), 'get', 'patch', 'put')

    def test_verbs(self):
        self._allowed_verbs(self.url, ('get', 'patch', 'put'))

    def test_not_allowed(self):
        eq_(self.anon.get(self.url).status_code, 403)

    def test_allowed(self):
        res = self.client.get(self.url)
        eq_(res.status_code, 200, res.content)
        data = json.loads(res.content)
        eq_(data['display_name'], self.user.display_name)

    def test_other(self):
        url = reverse('account-settings', kwargs={'pk': 10482})
        eq_(self.client.get(url).status_code, 403)

    def test_own(self):
        url = reverse('account-settings', kwargs={'pk': 'mine'})
        res = self.client.get(url)
        eq_(res.status_code, 200)
        data = json.loads(res.content)
        eq_(data['display_name'], self.user.display_name)

    def test_own_empty_name(self):
        self.user.update(display_name='')
        url = reverse('account-settings', kwargs={'pk': 'mine'})
        res = self.client.get(url)
        eq_(res.status_code, 200)
        data = json.loads(res.content)
        eq_(data['display_name'], 'user-2519')

    def test_patch(self):
        res = self.client.patch(
            self.url, data=json.dumps({'display_name': 'foo',
                                       'enable_recommendations': '0',
                                       'fxa_uid': 'f' * 32}))
        eq_(res.status_code, 200)
        user = UserProfile.objects.get(pk=self.user.pk)
        eq_(user.display_name, 'foo')
        eq_(user.enable_recommendations, False)
        eq_(user.fxa_uid, None)

    def test_patch_empty(self):
        res = self.client.patch(self.url,
                                data=json.dumps({'display_name': None}))
        eq_(res.status_code, 400)
        data = json.loads(res.content)
        eq_(data['display_name'], [u'This field is required'])

        res = self.client.patch(self.url,
                                data=json.dumps({'display_name': ''}))
        eq_(res.status_code, 400)
        data = json.loads(res.content)
        eq_(data['display_name'], [u'This field is required'])

    def test_put(self):
        res = self.client.put(
            self.url, data=json.dumps({'display_name': 'foo',
                                       'enable_recommendations': '0',
                                       'fxa_uid': 'f' * 32}))
        eq_(res.status_code, 200)
        user = UserProfile.objects.get(pk=self.user.pk)
        eq_(user.display_name, 'foo')
        eq_(user.enable_recommendations, False)
        eq_(user.fxa_uid, None)

    def test_patch_extra_fields(self):
        res = self.client.patch(self.url,
                                data=json.dumps({'display_name': 'foo',
                                                 'fxa_uid': 'f' * 32}))
        eq_(res.status_code, 200)
        user = UserProfile.objects.get(pk=self.user.pk)
        eq_(user.display_name, 'foo')  # Got changed successfully.
        eq_(user.fxa_uid, None)

    def test_patch_other(self):
        url = reverse('account-settings', kwargs={'pk': 10482})
        res = self.client.patch(url, data=json.dumps({'display_name': 'foo'}))
        eq_(res.status_code, 403)


class TestInstalled(RestOAuth):
    fixtures = fixture('user_2519', 'user_10482', 'webapp_337141')

    def setUp(self):
        super(TestInstalled, self).setUp()
        self.list_url = reverse('installed-apps')
        self.remove_app_url = reverse('installed-apps-remove')
        self.user = UserProfile.objects.get(pk=2519)

    def test_has_cors(self):
        self.assertCORS(self.client.post(self.remove_app_url), 'post')
        self.assertCORS(self.client.options(self.list_url), 'get')

    def test_verbs(self):
        self._allowed_verbs(self.list_url, ('get'))
        self._allowed_verbs(self.remove_app_url, ('post'))

    def test_not_allowed(self):
        eq_(self.anon.get(self.list_url).status_code, 403)

    def test_installed(self):
        ins = Installed.objects.create(user=self.user, webapp_id=337141)
        res = self.client.get(self.list_url)
        eq_(res.status_code, 200, res.content)
        data = json.loads(res.content)
        eq_(data['meta']['total_count'], 1)
        eq_(data['objects'][0]['id'], ins.webapp.pk)
        eq_(data['objects'][0]['user'],
            {'developed': False, 'purchased': False, 'installed': True})

    def test_installed_pagination(self):
        ins1 = Installed.objects.create(user=self.user, webapp=app_factory())
        ins1.update(created=self.days_ago(1))
        ins2 = Installed.objects.create(user=self.user, webapp=app_factory())
        ins2.update(created=self.days_ago(2))
        ins3 = Installed.objects.create(user=self.user, webapp=app_factory())
        ins3.update(created=self.days_ago(3))
        res = self.client.get(self.list_url, {'limit': 2})
        eq_(res.status_code, 200)
        data = json.loads(res.content)

        eq_(len(data['objects']), 2)
        eq_(data['objects'][0]['id'], ins1.webapp.id)
        eq_(data['objects'][1]['id'], ins2.webapp.id)
        eq_(data['meta']['total_count'], 3)
        eq_(data['meta']['limit'], 2)
        eq_(data['meta']['previous'], None)
        eq_(data['meta']['offset'], 0)
        next = urlparse(data['meta']['next'])
        eq_(next.path, self.list_url)
        eq_(QueryDict(next.query).dict(), {u'limit': u'2', u'offset': u'2'})

        res = self.client.get(self.list_url, {'limit': 2, 'offset': 2})
        eq_(res.status_code, 200)
        data = json.loads(res.content)

        eq_(len(data['objects']), 1)
        eq_(data['objects'][0]['id'], ins3.webapp.id)
        eq_(data['meta']['total_count'], 3)
        eq_(data['meta']['limit'], 2)
        prev = urlparse(data['meta']['previous'])
        eq_(next.path, self.list_url)
        eq_(QueryDict(prev.query).dict(), {u'limit': u'2', u'offset': u'0'})
        eq_(data['meta']['offset'], 2)
        eq_(data['meta']['next'], None)

    def test_installed_order(self):
        # Should be reverse chronological order.
        ins1 = Installed.objects.create(user=self.user, webapp=app_factory())
        ins1.update(created=self.days_ago(1))
        ins2 = Installed.objects.create(user=self.user, webapp=app_factory())
        ins2.update(created=self.days_ago(2))
        res = self.client.get(self.list_url)
        eq_(res.status_code, 200)
        data = json.loads(res.content)
        eq_(len(data['objects']), 2)
        eq_(data['objects'][0]['id'], ins1.webapp.id)
        eq_(data['objects'][1]['id'], ins2.webapp.id)

    def not_there(self):
        res = self.client.get(self.list_url)
        eq_(res.status_code, 200, res.content)
        data = json.loads(res.content)
        eq_(data['meta']['total_count'], 0)

    def test_installed_other(self):
        Installed.objects.create(user_id=10482, webapp_id=337141)
        self.not_there()

    def test_installed_reviewer(self):
        Installed.objects.create(user=self.user, webapp_id=337141,
                                 install_type=INSTALL_TYPE_REVIEWER)
        self.not_there()

    def test_installed_remove_app_anonymous(self):
        eq_(self.anon.get(self.remove_app_url).status_code, 403)
        eq_(self.anon.post(self.remove_app_url, {'app': 42}).status_code, 403)

    def test_installed_remove_app_not_installed(self):
        data = {'app': 4242}
        res = self.client.post(self.remove_app_url, json.dumps(data))
        eq_(res.status_code, 400)

        data = {}
        res = self.client.post(self.remove_app_url, json.dumps(data))
        eq_(res.status_code, 400)

    def test_installed_remove_app_get(self):
        eq_(self.client.get(self.remove_app_url).status_code, 405)

    def test_installed_remove_app(self):
        Installed.objects.create(user=self.user, webapp_id=337141)
        app = app_factory()
        Installed.objects.create(user=self.user, webapp=app)
        data = {'app': app.pk}
        res = self.client.post(self.remove_app_url, json.dumps(data))
        eq_(res.status_code, 202)
        # Make sure there are still 2 apps, but we removed one from the
        # installed list...
        eq_(Webapp.objects.count(), 2)
        eq_(list(self.user.installed_set.values_list('webapp_id', flat=True)),
            [337141])

    def test_installed_remove_app_not_user_installed(self):
        Installed.objects.create(user=self.user, webapp_id=337141)
        app = app_factory()
        Installed.objects.create(user=self.user, webapp=app,
                                 install_type=INSTALL_TYPE_REVIEWER)
        data = {'app': app.pk}
        res = self.client.post(self.remove_app_url, json.dumps(data))
        eq_(res.status_code, 400)


class FakeUUID(object):
    hex = '000000'


@patch.object(settings, 'SECRET_KEY', 'gubbish')
class TestLoginHandler(TestCase):

    def setUp(self):
        super(TestLoginHandler, self).setUp()
        self.url = reverse('account-login')
        self.logout_url = reverse('account-logout')

    def post(self, data):
        return self.client.post(self.url, json.dumps(data),
                                content_type='application/json')

    @patch.object(uuid, 'uuid4', FakeUUID)
    @patch('requests.post')
    def _test_login(self, http_request):
        FakeResponse = collections.namedtuple('FakeResponse',
                                              'status_code json')
        http_request.return_value = FakeResponse(
            200, lambda: {'status': 'okay', 'email': 'cvan@mozilla.com'})
        res = self.post({'assertion': 'fake-assertion',
                         'audience': 'fakemkt.org'})
        eq_(res.status_code, 201)
        data = json.loads(res.content)
        eq_(data['token'],
            'cvan@mozilla.com,95c9063d9f249aacfe5697fc83192ed6480c01463e2a80b3'
            '5af5ecaef11754700f4be33818d0e83a0cfc2cab365d60ba53b3c2b9f8f6589d1'
            'c43e9bbb876eef0,000000')

        return data

    def test_login_new_user_success(self):
        data = self._test_login()
        ok_(not any(data['permissions'].values()))

    def test_login_existing_user_success(self):
        profile = UserProfile.objects.create(email='cvan@mozilla.com',
                                             display_name='seavan')
        self.grant_permission(profile, 'Apps:Review')

        data = self._test_login()
        eq_(data['settings']['display_name'], 'seavan')
        eq_(data['settings']['email'], 'cvan@mozilla.com')
        eq_(data['settings']['enable_recommendations'], True)
        eq_(data['permissions'],
            {'admin': False,
             'developer': False,
             'localizer': False,
             'lookup': False,
             'curator': False,
             'reviewer': True,
             'webpay': False,
             'website_submitter': False,
             'stats': False,
             'revenue_stats': False,
             'content_tools_login': False,
             'content_tools_addon_submit': False,
             'content_tools_addon_review': False})
        eq_(data['apps']['installed'], [])
        eq_(data['apps']['purchased'], [])
        eq_(data['apps']['developed'], [])

    @patch('mkt.users.models.UserProfile.purchase_ids')
    def test_relevant_apps(self, purchase_ids):
        profile = UserProfile.objects.create(email='cvan@mozilla.com')
        purchased_app = app_factory()
        purchase_ids.return_value = [purchased_app.pk]
        developed_app = app_factory()
        developed_app.webappuser_set.create(user=profile)
        installed_app = app_factory()
        installed_app.installed.create(user=profile)

        data = self._test_login()
        eq_(data['apps']['installed'], [installed_app.pk])
        eq_(data['apps']['purchased'], [purchased_app.pk])
        eq_(data['apps']['developed'], [developed_app.pk])

    @patch('requests.post')
    def test_login_failure(self, http_request):
        FakeResponse = collections.namedtuple('FakeResponse',
                                              'status_code json')
        http_request.return_value = FakeResponse(
            200, lambda: {'status': 'busted'})
        res = self.post({'assertion': 'fake-assertion',
                         'audience': 'fakemkt.org'})
        eq_(res.status_code, 403)

    def test_login_empty(self):
        res = self.post({})
        data = json.loads(res.content)
        eq_(res.status_code, 400)
        assert 'assertion' in data
        assert 'apps' not in data

    def test_logout(self):
        UserProfile.objects.create(email='cvan@mozilla.com')
        data = self._test_login()

        r = self.client.delete(
            urlparams(self.logout_url, _user=data['token']),
            content_type='application/json')
        eq_(r.status_code, 204)


@patch.object(settings, 'SECRET_KEY', 'gubbish')
class TestFxaLoginHandler(TestCase):

    def setUp(self):
        super(TestFxaLoginHandler, self).setUp()
        self.url = reverse('fxa-account-login')
        self.logout_url = reverse('account-logout')

    def post(self, data):
        return self.client.post(self.url, json.dumps(data),
                                content_type='application/json')

    @patch.object(uuid, 'uuid4', FakeUUID)
    @patch('requests.post')
    def _test_login(self, http_request, state='fake-state'):
        with patch('mkt.account.views.OAuth2Session') as get_session:
            m = get_session()
            m.fetch_token.return_value = {'access_token': 'fake'}
            m.post().json.return_value = {
                'user': 'fake-uid',
                'email': 'cvan@mozilla.com'
            }
            res = self.post({
                'auth_response': 'https://testserver/?access_token=fake-token&'
                                 'code=coed&state=' + state,
                'state': state})
            eq_(res.status_code, 201)
            data = json.loads(res.content)
            eq_(data['token'],
                'cvan@mozilla.com,95c9063d9f249aacfe5697fc83192ed6480c01463e2a'
                '80b35af5ecaef11754700f4be33818d0e83a0cfc2cab365d60ba53b3c2b9f'
                '8f6589d1c43e9bbb876eef0,000000')
            return data

    def test_login_new_user_success(self):
        eq_(UserProfile.objects.count(), 0)
        data = self._test_login()
        ok_(not any(data['permissions'].values()))
        profile = UserProfile.objects.get()
        eq_(profile.email, 'cvan@mozilla.com')
        eq_(profile.fxa_uid, 'fake-uid')

    def test_login_existing_user_uid_success(self):
        profile = UserProfile.objects.create(fxa_uid='fake-uid',
                                             email='old@mozilla.com',
                                             display_name='seavan')
        self.grant_permission(profile, 'Apps:Review')

        data = self._test_login()
        profile.reload()
        eq_(profile.source, mkt.LOGIN_SOURCE_FXA)
        eq_(data['settings']['display_name'], 'seavan')
        eq_(data['settings']['email'], 'cvan@mozilla.com')
        eq_(data['settings']['enable_recommendations'], True)
        eq_(data['permissions'],
            {'admin': False,
             'developer': False,
             'localizer': False,
             'lookup': False,
             'curator': False,
             'reviewer': True,
             'webpay': False,
             'website_submitter': False,
             'stats': False,
             'revenue_stats': False,
             'content_tools_login': False,
             'content_tools_addon_submit': False,
             'content_tools_addon_review': False})
        eq_(data['apps']['installed'], [])
        eq_(data['apps']['purchased'], [])
        eq_(data['apps']['developed'], [])

        # Ensure user profile got updated with email.
        eq_(profile.email, 'cvan@mozilla.com')

        # Ensure fxa_uid stayed the same.
        eq_(profile.fxa_uid, 'fake-uid')

    @patch('mkt.users.models.UserProfile.purchase_ids')
    def test_relevant_apps(self, purchase_ids):
        profile = UserProfile.objects.create(email='cvan@mozilla.com',
                                             fxa_uid='fake-uid')
        purchased_app = app_factory()
        purchase_ids.return_value = [purchased_app.pk]
        developed_app = app_factory()
        developed_app.webappuser_set.create(user=profile)
        installed_app = app_factory()
        installed_app.installed.create(user=profile)

        data = self._test_login()
        eq_(data['apps']['installed'], [installed_app.pk])
        eq_(data['apps']['purchased'], [purchased_app.pk])
        eq_(data['apps']['developed'], [developed_app.pk])

    @patch('requests.post')
    def test_login_failure(self, http_request):
        with patch('mkt.account.views.OAuth2Session') as get_session:
            m = get_session()
            m.fetch_token.return_value = {'access_token': 'fake'}
            m.post().json.return_value = {'error': 'busted'}
            res = self.post({'auth_response': 'x',
                             'state': 'y'})
            eq_(res.status_code, 403)

    def test_login_empty(self):
        res = self.post({})
        data = json.loads(res.content)
        eq_(res.status_code, 400)
        assert 'auth_response' in data
        assert 'apps' not in data

    def test_login_settings(self):
        data = self._test_login()
        eq_(data['settings']['source'], 'firefox-accounts')

    @patch.object(uuid, 'uuid4', FakeUUID)
    @patch('requests.post')
    def test_login_sets_has_logged_in(self, http_request):
        state = 'fake-state'
        with patch('mkt.account.views.OAuth2Session') as get_session:
            m = get_session()
            m.fetch_token.return_value = {'access_token': 'fake'}
            m.post().json.return_value = {
                'user': 'fake-uid',
                'email': 'cvan@mozilla.com'
            }
            res = self.post({
                'auth_response': 'https://testserver/?access_token=fake-token&'
                                 'code=coed&state=' + state,
                'state': state})
            ok_('has_logged_in' in res.cookies)
            eq_(res.cookies['has_logged_in'].value, '1')

    def test_logout(self):
        data = self._test_login()

        r = self.client.delete(
            urlparams(self.logout_url, _user=data['token']),
            content_type='application/json')
        eq_(r.status_code, 204)


class TestFeedbackHandler(TestPotatoCaptcha, RestOAuth):

    def setUp(self):
        super(TestFeedbackHandler, self).setUp()
        self.url = reverse('account-feedback')
        self.user = UserProfile.objects.get(pk=2519)
        self.default_data = {
            'chromeless': 'no',
            'feedback': u'Hér€ is whàt I rælly think.',
            'platform': u'Desktøp',
            'from_url': '/feedback',
            'sprout': 'potato'
        }
        self.headers = {
            'HTTP_USER_AGENT': 'Fiiia-fox',
            'REMOTE_ADDR': '48.151.623.42'
        }

    def _call(self, anonymous=False, data=None):
        post_data = self.default_data.copy()
        client = self.anon if anonymous else self.client
        if data:
            post_data.update(data)
        res = client.post(self.url, data=json.dumps(post_data),
                          **self.headers)
        return res, json.loads(res.content)

    def _test_success(self, res, data):
        eq_(201, res.status_code)

        fields = self.default_data.copy()

        # PotatoCaptcha field shouldn't be present in returned data.
        del fields['sprout']
        ok_('sprout' not in data)

        # Rest of the fields should all be here.
        for name in fields.keys():
            eq_(fields[name], data[name])

        eq_(len(mail.outbox), 1)
        assert self.default_data['feedback'] in mail.outbox[0].body
        assert self.headers['REMOTE_ADDR'] in mail.outbox[0].body

    def test_send(self):
        res, data = self._call()
        self._test_success(res, data)
        eq_(unicode(self.user), data['user'])
        email = mail.outbox[0]
        eq_(email.from_email, settings.DEFAULT_FROM_EMAIL)
        eq_(email.extra_headers['Reply-To'], self.user.email)
        assert self.user.name in email.body
        assert unicode(self.user.pk) in email.body
        assert self.user.email in email.body

    def test_send_urlencode(self):
        self.headers['CONTENT_TYPE'] = 'application/x-www-form-urlencoded'
        post_data = self.default_data.copy()
        res = self.client.post(self.url, data=urlencode(post_data),
                               **self.headers)
        data = json.loads(res.content)
        self._test_success(res, data)
        eq_(unicode(self.user), data['user'])
        email = mail.outbox[0]
        eq_(email.from_email, settings.DEFAULT_FROM_EMAIL)
        eq_(email.extra_headers['Reply-To'], self.user.email)

    def test_send_without_platform(self):
        del self.default_data['platform']
        self.url += '?dev=platfoo'

        res, data = self._call()
        self._test_success(res, data)
        assert 'platfoo' in mail.outbox[0].body

    def test_send_anonymous(self):
        res, data = self._call(anonymous=True)
        self._test_success(res, data)
        assert not data['user']
        assert 'Anonymous' in mail.outbox[0].body
        eq_(settings.NOBODY_EMAIL, mail.outbox[0].from_email)

    def test_send_potato(self):
        tuber_res, tuber_data = self._call(data={'tuber': 'potat-toh'},
                                           anonymous=True)
        potato_res, potato_data = self._call(data={'sprout': 'potat-toh'},
                                             anonymous=True)
        self._test_bad_api_potato_data(tuber_res, tuber_data)
        self._test_bad_api_potato_data(potato_res, potato_data)

    def test_missing_optional_field(self):
        res, data = self._call(data={'platform': None})
        eq_(201, res.status_code)

    def test_send_bad_data(self):
        """
        One test to ensure that Feedback API is doing its validation duties.
        """
        res, data = self._call(data={'feedback': None})
        eq_(400, res.status_code)
        assert 'feedback' in data

    def test_bad_feedback_data(self):
        # test to ensure feedback with only white spaces are not submitted
        res, data = self._call(data={'feedback': '    '})
        eq_(400, res.status_code)
        assert 'feedback' in data


class TestNewsletter(RestOAuth):
    VALID_EMAIL = 'bob@example.com'
    VALID_PLUS_EMAIL = 'bob+totally+real@example.com'
    INVALID_EMAIL = '!not_an_email'

    def setUp(self):
        super(TestNewsletter, self).setUp()
        self.url = reverse('account-newsletter')

    @patch('basket.subscribe')
    def test_signup_bad(self, subscribe):
        res = self.client.post(self.url,
                               data=json.dumps({'email': self.INVALID_EMAIL}))
        eq_(res.status_code, 400)
        ok_(not subscribe.called)

    @patch('basket.subscribe')
    def test_signup_empty(self, subscribe):
        res = self.client.post(self.url)
        eq_(res.status_code, 400)
        ok_(not subscribe.called)

    @patch('basket.subscribe')
    def test_signup_invalid_newsletter(self, subscribe):
        res = self.client.post(self.url, data={'email': self.VALID_EMAIL,
                                               'lang': 'en-US',
                                               'newsletter': 'invalid'})
        eq_(res.status_code, 400)
        ok_(not subscribe.called)

    @patch('basket.subscribe')
    def test_signup_anonymous(self, subscribe):
        res = self.anon.post(self.url,
                             data=json.dumps({'email': self.VALID_EMAIL,
                                              'lang': 'en-US'}))
        eq_(res.status_code, 204)
        subscribe.assert_called_with(
            self.VALID_EMAIL, 'marketplace', lang='en-US',
            country='', trigger_welcome='Y', optin='Y', format='H')

    @patch('basket.subscribe')
    def test_signup_lang(self, subscribe):
        res = self.anon.post(self.url,
                             data=json.dumps({'email': self.VALID_EMAIL,
                                              'lang': 'es'}))
        eq_(res.status_code, 204)
        subscribe.assert_called_with(
            self.VALID_EMAIL, 'marketplace', lang='es',
            country='', trigger_welcome='Y', optin='Y', format='H')

    @patch('basket.subscribe')
    def test_signup(self, subscribe):
        res = self.client.post(self.url,
                               data=json.dumps({'email': self.VALID_EMAIL,
                                                'lang': 'en-US'}))
        eq_(res.status_code, 204)
        subscribe.assert_called_with(
            self.VALID_EMAIL, 'marketplace', lang='en-US',
            country='', trigger_welcome='Y', optin='Y', format='H')

    @patch('mkt.account.views.NewsletterView.get_region')
    @patch('basket.subscribe')
    def test_signup_us(self, subscribe, get_region):
        get_region.return_value = 'us'
        res = self.client.post(self.url,
                               data=json.dumps({'email': self.VALID_EMAIL,
                                                'lang': 'en-US'}))
        eq_(res.status_code, 204)
        subscribe.assert_called_with(
            self.VALID_EMAIL, 'marketplace', lang='en-US',
            country='us', trigger_welcome='Y', optin='Y', format='H')

    @patch('basket.subscribe')
    def test_signup_plus(self, subscribe):
        res = self.client.post(
            self.url,
            data=json.dumps({'email': self.VALID_PLUS_EMAIL,
                             'lang': 'en-US'}))
        subscribe.assert_called_with(
            self.VALID_PLUS_EMAIL, 'marketplace', lang='en-US',
            country='', trigger_welcome='Y', optin='Y', format='H')
        eq_(res.status_code, 204)

    @patch('basket.subscribe')
    def test_signup_about_apps(self, subscribe):
        res = self.client.post(self.url,
                               data=json.dumps({'email': self.VALID_EMAIL,
                                                'lang': 'en-US',
                                                'newsletter': 'about:apps'}))
        eq_(res.status_code, 204)
        subscribe.assert_called_with(
            self.VALID_EMAIL, 'mozilla-and-you,marketplace-desktop',
            lang='en-US', country='', trigger_welcome='Y',
            optin='Y', format='H')


class TestGroupsViewSet(RestOAuth):
    fixtures = fixture('user_2519', 'user_999')

    @classmethod
    def setUpTestData(cls):
        cls.target_user = UserProfile.objects.get(pk=999)
        cls.normal_group = Group.objects.create(name=u'NGr\u00F4up', rules="")
        cls.restricted_group = Group.objects.create(
            name=u'\u0158Group', rules="", restricted=True)
        cls.url = reverse('account-groups', kwargs={'pk': 999})

    def setUp(self):
        super(TestGroupsViewSet, self).setUp()
        self.grant_permission(self.user, 'Admin:%')

    def test_has_cors(self):
        self.assertCORS(self.client.get(self.url), 'get', 'delete', 'post')

    def test_verbs(self):
        self._allowed_verbs(self.url, ('get', 'delete', 'post'))

    def test_anon(self):
        eq_(self.anon.get(self.url).status_code, 403)

    def test_non_admin(self):
        self.remove_permission(self.user, 'Admin:%')
        eq_(self.client.get(self.url).status_code, 403)

    def test_list(self):
        GroupUser.objects.create(group=self.normal_group,
                                 user=self.target_user)
        GroupUser.objects.create(group=self.restricted_group,
                                 user=self.target_user)
        res = self.client.get(self.url)
        eq_(res.status_code, 200, res.content)
        data = json.loads(res.content)
        # Check target has those two groups.
        eq_(data[0]['id'], self.normal_group.pk)
        eq_(data[0]['name'], self.normal_group.name)
        eq_(data[0]['restricted'], self.normal_group.restricted)
        eq_(data[1]['id'], self.restricted_group.pk)
        eq_(data[1]['name'], self.restricted_group.name)
        eq_(data[1]['restricted'], self.restricted_group.restricted)

    def test_list_invalid_user_id(self):
        url = reverse('account-groups', kwargs={'pk': 54321})
        eq_(self.client.get(url).status_code, 400)

    def do_post(self, group_id):
        return self.client.post(self.url, data=json.dumps({'group': group_id}))

    def do_delete(self, group_id):
        return self.client.delete(self.url, data={'group': group_id})

    def test_add_group_valid(self):
        res = self.do_post(self.normal_group.pk)
        eq_(res.status_code, 201, res.content)

    def test_add_group_fail_admin(self):
        res = self.do_post(self.restricted_group.pk)
        eq_(res.status_code, 400, res.content)

    def test_add_group_fail_already_member(self):
        GroupUser.objects.create(group=self.normal_group,
                                 user=self.target_user)
        res = self.do_post(self.normal_group.pk)
        eq_(res.status_code, 400, res.content)

    def test_add_group_fail_no_group(self):
        res = self.do_post(123456)
        eq_(res.status_code, 400, res.content)

    def test_remove_group_valid(self):
        GroupUser.objects.create(group=self.normal_group,
                                 user=self.target_user)
        res = self.do_delete(self.normal_group.pk)
        eq_(res.status_code, 204, res.content)

    def test_remove_group_fail_admin(self):
        GroupUser.objects.create(group=self.restricted_group,
                                 user=self.target_user)
        res = self.do_delete(self.restricted_group.pk)
        eq_(res.status_code, 400, res.content)

    def test_remove_group_fail_not_member(self):
        res = self.do_delete(self.normal_group.pk)
        eq_(res.status_code, 400, res.content)

    def test_remove_group_fail_no_group(self):
        res = self.do_delete(123456)
        eq_(res.status_code, 400, res.content)
