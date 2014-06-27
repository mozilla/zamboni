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
