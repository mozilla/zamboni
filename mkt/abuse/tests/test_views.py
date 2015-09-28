# -*- coding: utf-8 -*-
import json

from django.core import mail
from django.core.urlresolvers import reverse
from django.utils.http import urlencode

from nose.tools import eq_

from mkt.abuse.models import AbuseReport
from mkt.api.tests.test_oauth import RestOAuth
from mkt.constants.base import STATUS_PUBLIC
from mkt.extensions.models import Extension
from mkt.site.fixtures import fixture
from mkt.webapps.models import Webapp
from mkt.users.models import UserProfile
from mkt.websites.utils import website_factory


class BaseTestAbuseResource(object):
    """
    Setup for AbuseResource tests that require inheritance from TestCase.
    """
    resource_name = None

    def setUp(self):
        super(BaseTestAbuseResource, self).setUp()
        self.list_url = reverse('%s-abuse-list' % (self.resource_name,))
        self.headers = {
            'REMOTE_ADDR': '48.151.623.42'
        }


class AbuseResourceTests(object):
    """
    Setup for AbuseResource tests that do not require inheritance from
    TestCase.

    Separate from BaseTestAbuseResource to ensure that test_* methods of this
    abstract base class are not discovered by the runner.
    """
    default_data = None

    def _call(self, anonymous=False, data=None):
        post_data = self.default_data.copy()
        if anonymous:
            post_data['tuber'] = ''
            post_data['sprout'] = 'potato'
        if data:
            post_data.update(data)

        client = self.anon if anonymous else self.client
        res = client.post(self.list_url, data=urlencode(post_data),
                          content_type='application/x-www-form-urlencoded',
                          **self.headers)
        try:
            res_data = json.loads(res.content)

        # Pending #855817, some errors will return an empty response body.
        except ValueError:
            res_data = res.content

        return res, res_data

    def _test_success(self, res, data):
        """
        Tests common when looking to ensure complete successful responses.
        """
        eq_(201, res.status_code, res.content)
        fields = self.default_data.copy()

        del fields['sprout']

        if 'user' in fields:
            eq_(data.pop('user')['display_name'], self.user.display_name)
            del fields['user']
        if 'app' in fields:
            eq_(int(data.pop('app')['id']), self.app.pk)
            del fields['app']
        if 'website' in fields:
            eq_(int(data.pop('website')['id']), self.website.pk)
            del fields['website']
        if 'extension' in fields:
            eq_(int(data.pop('extension')['id']), self.extension.pk)
            del fields['extension']

        for name in fields.keys():
            eq_(fields[name], data[name])

        newest_report = AbuseReport.objects.order_by('-id')[0]
        eq_(newest_report.message, data['text'])
        eq_(newest_report.ip_address, self.headers['REMOTE_ADDR'])

        eq_(len(mail.outbox), 1)
        assert self.default_data['text'] in mail.outbox[0].body

    def test_get(self):
        res = self.client.get(self.list_url)
        eq_(res.status_code, 405)

    def test_send(self):
        res, data = self._call()
        self._test_success(res, data)
        assert 'display_name' in data['reporter']
        assert 'ip_address' not in data

    def test_send_anonymous(self):
        res, data = self._call(anonymous=True)
        self._test_success(res, data)
        eq_(data['reporter'], None)
        assert 'ip_address' not in data

    def test_send_potato(self):
        tuber_res, tuber_data = self._call(data={'tuber': 'potat-toh'},
                                           anonymous=True)
        potato_res, potato_data = self._call(data={'sprout': 'potat-toh'},
                                             anonymous=True)
        eq_(tuber_res.status_code, 400)
        eq_(potato_res.status_code, 400)


class TestUserAbuseResource(AbuseResourceTests, BaseTestAbuseResource,
                            RestOAuth):
    resource_name = 'user'

    def setUp(self):
        super(TestUserAbuseResource, self).setUp()
        self.user = UserProfile.objects.get(pk=2519)
        self.default_data = {
            'text': '@cvan is very abusive.',
            'sprout': 'potato',
            'user': self.user.pk
        }

    def test_invalid_user(self):
        res, data = self._call(data={'user': '-1'})
        eq_(400, res.status_code)
        assert 'Invalid' in data['user'][0]


class TestAppAbuseResource(AbuseResourceTests, BaseTestAbuseResource,
                           RestOAuth):
    fixtures = RestOAuth.fixtures + fixture('webapp_337141')
    resource_name = 'app'

    def setUp(self):
        super(TestAppAbuseResource, self).setUp()
        self.app = Webapp.objects.get(pk=337141)
        self.default_data = {
            'text': "@cvan's app is very abusive.",
            'sprout': 'potato',
            'app': self.app.pk
        }

    def test_invalid_app(self):
        res, data = self._call(data={'app': -1})
        eq_(400, res.status_code)
        assert 'does not exist' in data['app'][0]

    def test_slug_app(self):
        res, data = self._call(data={'app': self.app.app_slug})
        eq_(201, res.status_code)


class TestWebsiteAbuseResource(AbuseResourceTests, BaseTestAbuseResource,
                               RestOAuth):
    resource_name = 'website'

    def setUp(self):
        super(TestWebsiteAbuseResource, self).setUp()
        self.website = website_factory()
        self.default_data = {
            'text': 'This website is weird.',
            'sprout': 'potato',
            'website': self.website.pk
        }

    def test_invalid_website(self):
        res, data = self._call(data={'website': self.website.pk + 42})
        eq_(400, res.status_code)
        assert 'does not exist' in data['website'][0]


class TestExtensionAbuseResource(AbuseResourceTests, BaseTestAbuseResource,
                                 RestOAuth):
    resource_name = 'extension'

    def setUp(self):
        super(TestExtensionAbuseResource, self).setUp()
        self.extension = Extension.objects.create(
            name=u'Test Êxtension')
        self.extension.update(status=STATUS_PUBLIC)
        self.default_data = {
            'text': 'Lies! This extension is an add-on!',
            'sprout': 'potato',
            'extension': self.extension.pk
        }

    def test_invalid_extension(self):
        res, data = self._call(data={'extension': -1})
        eq_(400, res.status_code)
        assert 'does not exist' in data['extension'][0]

    def test_deleted_extension(self):
        data = {'extension': self.extension.slug}
        self.extension.delete()
        res, data = self._call(data=data)
        eq_(400, res.status_code)
        assert 'does not exist' in data['extension'][0]

    def test_slug_extension(self):
        res, data = self._call(data={'extension': self.extension.slug})
        eq_(201, res.status_code)
