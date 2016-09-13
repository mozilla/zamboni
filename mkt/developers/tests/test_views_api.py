# -*- coding: utf-8 -*-
import json
import uuid

from django.core.urlresolvers import NoReverseMatch
from django.core.urlresolvers import reverse

import mock
from jingo.helpers import urlparams
from nose.tools import eq_

import mkt
from mkt.api.models import Access
from mkt.api.tests.test_oauth import RestOAuth
from mkt.developers.models import IARCRequest
from mkt.site.fixtures import fixture
from mkt.site.helpers import absolutify
from mkt.site.tests import TestCase
from mkt.site.utils import app_factory
from mkt.webapps.models import ContentRating, Webapp
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

    def test_get_content_ratings_since(self):
        old_date = self.days_ago(100)
        cr = ContentRating.objects.create(addon=self.app, ratings_body=0,
                                          rating=0)
        # Pass _signal=False to avoid django auto-now on modified.
        cr.update(modified=old_date, _signal=False)
        eq_(cr.modified, old_date)

        res = self.client.get(urlparams(
            reverse('content-ratings-list', args=[self.app.app_slug]),
            since=self.days_ago(5)))
        eq_(res.status_code, 404)

        cr.update(modified=self.days_ago(1))
        res = self.client.get(urlparams(
            reverse('content-ratings-list', args=[self.app.id]),
            since=self.days_ago(5)))
        eq_(res.status_code, 200)
        eq_(len(json.loads(res.content)['objects']), 1)

    def test_view_allowed(self):
        """Only -list, no create/update/delete."""
        with self.assertRaises(NoReverseMatch):
            reverse('content-ratings-create', args=[self.app.id])
        with self.assertRaises(NoReverseMatch):
            reverse('content-ratings-update', args=[self.app.id])
        with self.assertRaises(NoReverseMatch):
            reverse('content-ratings-delete', args=[self.app.id])
        reverse('content-ratings-list', args=[self.app.app_slug])


@mock.patch('mkt.webapps.models.Webapp.details_complete', lambda self: True)
class TestContentRatingPingback(RestOAuth):
    def setUp(self):
        super(TestContentRatingPingback, self).setUp()
        self.app = app_factory(status=mkt.STATUS_NULL)
        self.app.addonuser_set.create(user=self.profile)
        self.url = reverse('content-ratings-pingback')

    def test_has_cors(self):
        res = self.anon.post(self.url, data=json.dumps({}))
        self.assertCORS(res, 'post')

    def test_post_no_store_request_id(self):
        res = self.anon.post(self.url, data=json.dumps({}))
        eq_(res.status_code, 400)
        eq_(res.data, {'detail': 'Need a StoreRequestID',
                       'StatusCode': 'InvalidRequest'})

    def test_post_store_request_id_is_not_an_uuid(self):
        res = self.anon.post(self.url, data=json.dumps(
            {'StoreRequestID': 'garbage'}))
        eq_(res.status_code, 400)
        eq_(res.data, {'detail': 'StoreRequestID is not a valid UUID',
                       'StatusCode': 'InvalidRequest'})

    def test_post_store_request_id_not_found(self):
        res = self.anon.post(self.url, data=json.dumps(
            {'StoreRequestID': unicode(uuid.uuid4())}))
        eq_(res.status_code, 404)
        eq_(res.data, {'detail': 'Not found.', 'StatusCode': 'InvalidRequest'})

    def test_post_error(self):
        request = IARCRequest.objects.create(app=self.app)
        res = self.anon.post(self.url, data=json.dumps(
            {'StoreRequestID': request.uuid}))
        eq_(res.status_code, 400)
        eq_(res.data,
            {'RatingList': 'This field is required.',
             'StatusCode': 'InvalidRequest'})

    def test_post_success_uuid_without_separators(self):
        request = IARCRequest.objects.create(app=self.app)
        self._test_post_success(unicode(request.uuid))

    def test_post_success_uuid_with_separators(self):
        request = IARCRequest.objects.create(app=self.app)
        self._test_post_success(unicode(uuid.UUID(request.uuid)))

    def _test_post_success(self, store_request_uuid):
        data = {
            'StoreRequestID': store_request_uuid,
            'CertID': unicode(uuid.uuid4()),
            'RatingList': [
                {
                    'RatingAuthorityShortText': 'Generic',
                    'AgeRatingText': '12+',
                    'DescriptorList': [{'DescriptorText': 'PEGI_Violence'}],
                    'InteractiveElementList': [
                        {'InteractiveElementText': 'IE_UsersInteract'},
                    ]
                },
                {
                    'RatingAuthorityShortText': 'ESRB',
                    'AgeRatingText': 'Teen',
                    'DescriptorList': [],
                    'InteractiveElementList': []
                },
            ]
        }
        eq_(self.app.is_fully_complete(), False)  # Missing ratings.
        res = self.anon.post(self.url, data=json.dumps(data))
        eq_(res.status_code, 200)
        eq_(res.data,
            {'StoreProductID': self.app.guid,
             'StoreProductURL': absolutify(self.app.get_url_path()),
             'EmailAddress': self.profile.email,
             'CompanyName': u'',
             'StoreDeveloperID': self.app.pk,
             'StatusCode': 'Success',
             'DeveloperEmail': self.profile.email,
             'Publish': False,
             'ProductName': self.app.name})
        # Don't use .reload(), it doesn't clear cached one-to-one relations.
        self.app = Webapp.objects.get(pk=self.app.pk)
        with self.assertRaises(IARCRequest.DoesNotExist):
            self.app.iarc_request
        eq_(self.app.status, mkt.STATUS_PENDING)
        eq_(self.app.is_fully_complete(), True)
        eq_(uuid.UUID(self.app.iarc_cert.cert_id), uuid.UUID(data['CertID']))
        eq_(self.app.get_content_ratings_by_body(),
            {'generic': '12', 'esrb': '13'})
        self.assertSetEqual(
            self.app.rating_descriptors.to_keys(), ['has_generic_violence'])
        self.assertSetEqual(
            self.app.rating_interactives.to_keys(), ['has_users_interact'])
