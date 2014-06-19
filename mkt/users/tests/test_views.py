# -*- coding: utf-8 -*-
import json
from datetime import datetime
import urllib

from django.test.utils import override_settings

import mock
from nose.tools import eq_, ok_
from waffle import helpers  # NOQA

import amo
import amo.tests
from amo.helpers import urlparams
from amo.pyquery_wrapper import PyQuery as pq
from amo.urlresolvers import reverse
from mkt.site.fixtures import fixture
from mkt.users.models import UserProfile


class TestAjax(amo.tests.TestCase):
    fixtures = fixture('user_999')

    def setUp(self):
        super(TestAjax, self).setUp()
        self.user = UserProfile.objects.get(email='regular@mozilla.com')
        ok_(self.client.login(username=self.user.email, password='password'))

    def test_ajax_404(self):
        r = self.client.get(reverse('users.ajax'), follow=True)
        eq_(r.status_code, 404)

    def test_ajax_success(self):
        u = UserProfile.objects.create(email='ajax@mozilla.com',
            username=u'àjæx', read_dev_agreement=datetime.now())
        r = self.client.get(reverse('users.ajax'), {'q': 'ajax@mozilla.com'},
                            follow=True)
        data = json.loads(r.content)
        eq_(data, {'status': 1, 'message': '', 'name': u'\xe0j\xe6x',
                   'id': u.id})

    def test_ajax_xss(self):
        self.user.display_name = '<script>alert("xss")</script>'
        self.user.save()
        assert '<script>' in self.user.display_name, (
            'Expected <script> to be in display name')
        r = self.client.get(reverse('users.ajax'),
                            {'q': self.user.email, 'dev': 0})
        assert '<script>' not in r.content
        assert '&lt;script&gt;' in r.content

    def test_ajax_failure_incorrect_email_mkt(self):
        res = self.client.get(reverse('users.ajax'), {'q': 'incorrect'},
                              follow=True)
        data = json.loads(res.content)
        eq_(data,
            {'status': 0,
             'message': 'A user with that email address does not exist, or the'
                        ' user has not yet accepted the developer agreement.'})

    def test_ajax_failure_no_email(self):
        r = self.client.get(reverse('users.ajax'), {'q': ''}, follow=True)
        data = json.loads(r.content)
        eq_(data,
            {'status': 0,
             'message': 'An email address is required.'})

    def test_forbidden(self):
        self.client.logout()
        r = self.client.get(reverse('users.ajax'))
        eq_(r.status_code, 401)


class TestLogout(amo.tests.TestCase):
    fixtures = fixture('user_999')

    def setUp(self):
        super(TestLogout, self).setUp()
        self.user = UserProfile.objects.get(email='regular@mozilla.com')
        ok_(self.client.login(username=self.user.email, password='password'))

    def test_success(self):
        res = self.client.get('/developers/', follow=True)
        data = pq(res.content.decode('utf-8'))('body').attr('data-user')
        data = json.loads(data)
        eq_(data['email'], self.user.email)
        eq_(data['anonymous'], False)

        res = self.client.get(reverse('users.logout'), follow=True)
        data = pq(res.content.decode('utf-8'))('body').attr('data-user')
        data = json.loads(data)
        eq_(data['email'], '')
        eq_(data['anonymous'], True)

    def test_redirect(self):
        url = '/developers/'
        res = self.client.get(urlparams(reverse('users.logout'), to=url),
                            follow=True)
        self.assertRedirects(res, url, status_code=302)

        # Test that we don't follow domains
        url = urlparams(reverse('users.logout'), to='http://ev.il/developers/')
        res = self.client.get(url, follow=True)
        self.assertRedirects(res, '/', status_code=302)


class TestAlreadyLoggedIn(amo.tests.TestCase):
    fixtures = fixture('user_999')

    def setUp(self):
        super(TestAlreadyLoggedIn, self).setUp()
        self.url = reverse('users.login')
        self.user = UserProfile.objects.get(email='regular@mozilla.com')
        ok_(self.client.login(username=self.user.email, password='password'))

    def test_double_login(self):
        # If you go to the login page when you're already logged in we bounce
        # you.
        r = self.client.get(self.url, follow=True)
        self.assert3xx(r, '/')

    def test_ok_redirects(self):
        r = self.client.get(self.url + '?to=/developers/submit/terms/', follow=True)
        self.assert3xx(r, '/developers/submit/terms')

    def test_bad_redirects(self):
        for redirect in ['http://xx.com',
                         'data:text/html,<script>window.alert("xss")</script>',
                         'mailto:test@example.com',
                         'file:///etc/passwd',
                         'javascript:window.alert("xss");']:
            r = self.client.get(self.url + '?to=' + redirect, follow=True)
            self.assert3xx(r, '/')


class LoginPageTests(amo.tests.TestCase):
    fixtures = fixture('user_999')

    def setUp(self):
        super(LoginPageTests, self).setUp()
        self.url = reverse('users.login')

    def test_login_link(self):
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        sel = pq(r.content)('.proceed .button')
        eq_(sel.length, 1)
        eq_(sel[0].get('href'), '#')

    def test_fxa_login_redirect(self):
        self.create_switch('firefox-accounts')
        r = self.client.get(self.url + '?to=/developers/submit/terms')
        sel = pq(r.content)('.proceed .button')
        eq_(sel.length, 1)
        eq_(urllib.unquote(sel[0].get('href')),
            '/fxa/login/?to=/developers/submit/terms')


class LoginHeaderTests(amo.tests.TestCase):
    fixtures = fixture('user_999')

    def setUp(self):
        super(LoginHeaderTests, self).setUp()
        self.url = reverse('ecosystem.landing')

    def test_login_link(self):
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        sel = pq(r.content)('#site-header .browserid')
        eq_(sel.length, 1)
        eq_(sel[0].get('href'), '#')

    def test_fxa_login_link(self):
        self.create_switch('firefox-accounts')
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        sel = pq(r.content)('#site-header .browserid')
        eq_(sel.length, 1)
        eq_(urllib.unquote(sel[0].get('href')), '/fxa/login/?to=/developers/')


class FirefoxAccountTests(amo.tests.TestCase):
    fixtures = fixture('user_999')

    def setUp(self):
        super(FirefoxAccountTests, self).setUp()
        self.create_switch('firefox-accounts')

    @override_settings(FXA_OAUTH_URL='https://fxa.example.com')
    def test_fxa_login_redirect(self):
        url = reverse('fxa_login')
        r = self.client.get(url)
        eq_(r.status_code, 302)
        ok_(urllib.unquote(r['location']).startswith(
            'https://fxa.example.com/v1/authorization?'))

    def do_authorize(self, args):
        with mock.patch('mkt.users.views.get_fxa_session') as get_session:
            m = get_session()
            m.fetch_token.return_value = {'access_token': 'fake'}
            m.post().json.return_value = {
                'user': 'fake-uid',
                'email': 'regular@mozilla.com'
            }
            url = reverse('fxa_authorize')
            return self.client.get(url, args)

    @override_settings(FXA_OAUTH_URL='https://fxa.example.com')
    def test_fxa_authorize(self):
        self.client.get(reverse('fxa_login'))
        r = self.do_authorize({})
        eq_(r.status_code, 302)
        eq_(r['location'], 'http://testserver/')

    @override_settings(FXA_OAUTH_URL='https://fxa.example.com')
    def test_fxa_authorize_redirect_to(self):
        self.client.get(reverse('fxa_login'),
                        {'to': '/developers/terms'})
        r = self.do_authorize({})
        eq_(r.status_code, 302)
        eq_(r['location'], 'http://testserver/developers/terms')

    @override_settings(FXA_OAUTH_URL='https://fxa.example.com')
    def test_fxa_authorize_no_login(self):
        r = self.do_authorize({})
        eq_(r.status_code, 400)

    @override_settings(FXA_OAUTH_URL='https://fxa.example.com')
    def test_fxa_authorize_newaccount(self):
        self.client.get(reverse('fxa_login'))

        with mock.patch('mkt.users.views.get_fxa_session') as get_session:
            m = get_session()
            m.fetch_token.return_value = {'access_token': 'fake'}
            m.post().json.return_value = {
                'user': 'fake-uid',
                'email': 'newacct@mozilla.com'
            }
            url = reverse('fxa_authorize')
            r = self.client.get(url)
        eq_(r.status_code, 302)
        eq_(r['location'], 'http://testserver/')
        eq_(UserProfile.objects.filter(email='newacct@mozilla.com',
                                       username='fake-uid').count(), 1)
