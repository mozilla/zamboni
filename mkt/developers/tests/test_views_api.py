# -*- coding: utf-8 -*-
import json

from django.core.urlresolvers import NoReverseMatch
from django.core.urlresolvers import reverse

from nose.tools import eq_

import mkt
from mkt.api.models import Access
from mkt.site.fixtures import fixture
from mkt.site.tests import TestCase
from mkt.site.utils import app_factory
from mkt.webapps.models import ContentRating
from mkt.users.models import UserProfile


class TestAPI(TestCase):
    fixtures = fixture('user_999')

    def setUp(self):
        self.profile = UserProfile.objects.get(pk=999)
        self.user = self.profile
        self.login(self.profile)
        self.url = reverse('mkt.developers.apps.api')

    def test_logged_out(self):
        self.client.logout()
        self.assertLoginRequired(self.client.get(self.url))

    def test_create(self):
        Access.objects.create(user=self.user, key='foo', secret='bar')
        res = self.client.post(
            self.url,
            {'app_name': 'test', 'redirect_uri': 'https://example.com/myapp',
             'oauth_leg': 'website'})
        self.assertNoFormErrors(res)
        eq_(res.status_code, 200)
        consumers = Access.objects.filter(user=self.user)
        eq_(len(consumers), 2)
        eq_(consumers[1].key, 'mkt:999:regular@mozilla.com:1')

    def test_delete(self):
        a = Access.objects.create(user=self.user, key='foo', secret='bar')
        res = self.client.post(self.url, {'delete': 'yep', 'consumer': a.pk})
        eq_(res.status_code, 200)
        eq_(Access.objects.filter(user=self.user).count(), 0)

    def test_delete_other_user(self):
        Access.objects.create(user=self.user, key='foo', secret='bar')
        other_user = UserProfile.objects.create(email='a@a.com')
        other_token = Access.objects.create(user=other_user, key='boo',
                                            secret='far')
        res = self.client.post(self.url, {'delete': 'yep',
                                          'consumer': other_token.pk})
        eq_(res.status_code, 200)
        eq_(Access.objects.count(), 2)

    def test_admin(self):
        self.grant_permission(self.profile, 'What:ever', name='Admins')
        res = self.client.post(self.url)
        eq_(res.status_code, 200)
        eq_(Access.objects.filter(user=self.user).count(), 0)


class TestContentRating(TestCase):

    def setUp(self):
        self.app = app_factory()

    def test_get_content_ratings(self):
        for body in (mkt.ratingsbodies.CLASSIND, mkt.ratingsbodies.ESRB):
            ContentRating.objects.create(addon=self.app, ratings_body=body.id,
                                         rating=0)
        res = self.client.get(reverse('content-ratings-list',
                                      args=[self.app.app_slug]))
        eq_(res.status_code, 200)

        res = json.loads(res.content)
        eq_(len(res['objects']), 2)
        rating = res['objects'][0]
        eq_(rating['body'], 'classind')
        eq_(rating['rating'], '0')

    def test_view_allowed(self):
        """Only -list, no create/update/delete."""
        with self.assertRaises(NoReverseMatch):
            reverse('content-ratings-create', args=[self.app.id])
        with self.assertRaises(NoReverseMatch):
            reverse('content-ratings-update', args=[self.app.id])
        with self.assertRaises(NoReverseMatch):
            reverse('content-ratings-delete', args=[self.app.id])
        reverse('content-ratings-list', args=[self.app.app_slug])
