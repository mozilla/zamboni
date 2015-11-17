# -*- coding: utf-8 -*-
import json
from datetime import datetime, timedelta

from django.conf import settings
from django.core.cache import cache
from django.core.urlresolvers import reverse
from django.test.client import RequestFactory

import mock
from cache_nuggets.lib import Token
from nose.tools import eq_, ok_

import mkt
import mkt.regions
from mkt.access.models import GroupUser
from mkt.api.models import Access
from mkt.api.tests.test_oauth import RestOAuth, RestOAuthClient
from mkt.constants.features import FeatureProfile
from mkt.reviewers.models import (AdditionalReview, CannedResponse,
                                  EscalationQueue, QUEUE_TARAKO,
                                  RereviewQueue, ReviewerScore)
from mkt.reviewers.utils import AppsReviewing
from mkt.site.fixtures import fixture
from mkt.site.tests import ESTestCase
from mkt.tags.models import Tag
from mkt.users.models import UserProfile
from mkt.webapps.models import Webapp
from mkt.websites.utils import website_factory


class TestReviewing(RestOAuth):
    fixtures = fixture('user_2519', 'webapp_337141')

    def setUp(self):
        super(TestReviewing, self).setUp()
        self.list_url = reverse('reviewing-list')
        self.user = UserProfile.objects.get(pk=2519)
        self.req = RequestFactory().get('/')
        self.req.user = self.user

    def test_verbs(self):
        self._allowed_verbs(self.list_url, ('get'))

    def test_not_allowed(self):
        eq_(self.anon.get(self.list_url).status_code, 403)

    def test_still_not_allowed(self):
        eq_(self.client.get(self.list_url).status_code, 403)

    def add_perms(self):
        self.grant_permission(self.user, 'Apps:Review')

    def test_allowed(self):
        self.add_perms()
        res = self.client.get(self.list_url)
        eq_(res.status_code, 200, res.content)
        data = json.loads(res.content)
        eq_(data['objects'], [])

    def test_some(self):
        self.add_perms()

        # This feels rather brittle.
        cache.set('%s:review_viewing:%s' % (settings.CACHE_PREFIX, 337141),
                  2519, 50 * 2)
        AppsReviewing(self.req).add(337141)

        res = self.client.get(self.list_url)
        data = json.loads(res.content)
        eq_(data['objects'][0]['resource_uri'],
            reverse('app-detail', kwargs={'pk': 337141}))


class TestApiReviewerSearch(RestOAuth, ESTestCase):
    fixtures = fixture('webapp_337141', 'user_2519')

    def setUp(self):
        super(TestApiReviewerSearch, self).setUp()
        self.user = UserProfile.objects.get(pk=2519)
        self.profile = self.user
        self.profile.update(read_dev_agreement=datetime.now())
        self.grant_permission(self.profile, 'Apps:Review')

        self.access = Access.objects.create(
            key='test_oauth_key', secret='ultra secret', user=self.user)
        self.url = reverse('reviewers-search-api')

        self.webapp = Webapp.objects.get(pk=337141)
        self.webapp.addondevicetype_set.create(device_type=mkt.DEVICE_GAIA.id)
        self.webapp.update(status=mkt.STATUS_PENDING)
        self.refresh('webapp')

    def test_fields(self):
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        self.assertSetEqual(
            obj.keys(),
            ['device_types', 'id', 'is_escalated',
             'is_packaged', 'latest_version', 'name', 'premium_type', 'price',
             'slug', 'status'])
        eq_(obj['latest_version']['status'], 4)

    def test_anonymous_access(self):
        res = self.anon.get(self.url)
        eq_(res.status_code, 403)

    def test_non_reviewer_access(self):
        GroupUser.objects.filter(group__rules='Apps:Review',
                                 user=self.profile).delete()
        res = self.client.get(self.url)
        eq_(res.status_code, 403)

    def test_owner_still_non_reviewer_access(self):
        user = Webapp.objects.get(pk=337141).authors.all()[0]
        access = Access.objects.create(
            key='test_oauth_key_owner', secret='super secret', user=user)
        client = RestOAuthClient(access)
        res = client.get(self.url)
        eq_(res.status_code, 403)

    def test_status(self):
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

        res = self.client.get(self.url, {'status': 'pending'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

        res = self.client.get(self.url, {'status': 'rejected'})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 0)

        self.webapp.update(status=mkt.STATUS_REJECTED)
        self.refresh('webapp')

        res = self.client.get(self.url, {'status': 'rejected'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

        self.webapp.update(status=mkt.STATUS_PUBLIC)
        self.refresh('webapp')

        res = self.client.get(self.url, {'status': 'public'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

        res = self.client.get(self.url, {'status': 'any'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

        res = self.client.get(self.url, {'status': 'vindaloo'})
        eq_(res.status_code, 400)
        error = res.json['detail']
        eq_(error.keys(), ['status'])

    def test_is_escalated(self):
        res = self.client.get(self.url, {'is_escalated': True})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 0)

        res = self.client.get(self.url, {'is_escalated': False})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

        res = self.client.get(self.url, {'is_escalated': None})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

    def test_is_tarako(self):
        Tag(tag_text='tarako').save_tag(self.webapp)
        self.webapp.save()
        self.refresh('webapp')

        res = self.client.get(self.url, {'is_tarako': True})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

        res = self.client.get(self.url, {'is_tarako': False})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 0)

        res = self.client.get(self.url, {'is_tarako': None})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

    def test_has_editors_comment(self):
        res = self.client.get(self.url, {'has_editor_comment': True})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 0)

        res = self.client.get(self.url, {'has_editor_comment': False})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

        res = self.client.get(self.url, {'has_editor_comment': None})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

    def test_has_info_request(self):
        res = self.client.get(self.url, {'has_info_request': True})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 0)

        res = self.client.get(self.url, {'has_info_request': False})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

        res = self.client.get(self.url, {'has_info_request': None})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

    def test_no_region_filtering(self):
        self.webapp.addonexcludedregion.create(region=mkt.regions.BRA.id)
        self.webapp.save()
        self.refresh('webapp')

        res = self.client.get(self.url, {'region': 'br'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

    def test_no_feature_profile_filtering(self):
        feature_profile = FeatureProfile().to_signature()
        qs = {'q': 'something', 'pro': feature_profile, 'dev': 'firefoxos'}

        # Enable an app feature that doesn't match one in our profile.
        self.webapp.latest_version.features.update(has_pay=True)
        self.webapp.save()
        self.refresh('webapp')

        res = self.client.get(self.url, qs)
        eq_(res.status_code, 200)
        eq_(len(res.json['objects']), 1)
        obj = res.json['objects'][0]
        eq_(obj['slug'], self.webapp.app_slug)

    def test_dev_and_device_filtering(self):
        res = self.client.get(self.url, {'dev': 'firefoxos'})
        eq_(res.status_code, 200)
        eq_(len(res.json['objects']), 1)

        res = self.client.get(self.url, {'dev_and_device': 'firefoxos'})
        eq_(res.status_code, 200)
        eq_(len(res.json['objects']), 1)

        res = self.client.get(self.url, {'dev_and_device': 'android-mobile'})
        eq_(res.status_code, 200)
        eq_(len(res.json['objects']), 0)

        self.webapp.addondevicetype_set.create(
            device_type=mkt.DEVICE_TABLET.id)
        self.webapp.save()
        self.refresh('webapp')
        res = self.client.get(self.url, {'dev_and_device': 'android-mobile'})
        eq_(res.status_code, 200)
        eq_(len(res.json['objects']), 0)

        self.webapp.addondevicetype_set.create(
            device_type=mkt.DEVICE_MOBILE.id)
        self.webapp.save()
        self.refresh('webapp')
        res = self.client.get(self.url, {'dev_and_device': 'android-mobile'})
        eq_(res.status_code, 200)
        eq_(len(res.json['objects']), 1)

    def test_no_premium_filtering(self):
        self.webapp.addondevicetype_set.create(
            device_type=mkt.DEVICE_MOBILE.id)
        self.webapp.update(premium_type=mkt.ADDON_PREMIUM)
        self.refresh('webapp')
        res = self.client.get(self.url, {'dev': 'android', 'device': 'mobile'})
        eq_(res.status_code, 200)
        eq_(len(res.json['objects']), 1)


class TestWebsiteReviewerActions(RestOAuth):
    fixtures = fixture('user_2519')

    def setUp(self):
        super(TestWebsiteReviewerActions, self).setUp()
        self.website = website_factory(
            title='something',
            categories=json.dumps(['books', 'sports']))
        self.user = UserProfile.objects.get(pk=2519)
        self.grant_permission(self.user, 'Websites:Review')

    def postit(self, view):
        url = reverse('website-' + view, kwargs={'pk': self.website.pk})
        return self.client.post(url)

    def test_anon(self):
        r = self.anon.post(
            reverse('website-approve', kwargs={'pk': self.website.pk}))
        eq_(r.status_code, 403)

    def test_no_perms(self):
        self.remove_permission(self.user, 'Websites:Review')
        res = self.postit('approve')
        eq_(res.status_code, 403)

    def test_approve(self):
        self.website.status = mkt.STATUS_PENDING
        res = self.postit('approve')
        eq_(res.status_code, 200)
        eq_(self.website.reload().status, mkt.STATUS_PUBLIC)

    def test_reject(self):
        self.website.status = mkt.STATUS_PENDING
        res = self.postit('reject')
        eq_(res.status_code, 200)
        eq_(self.website.reload().status, mkt.STATUS_REJECTED)


class TestApproveRegion(RestOAuth):
    fixtures = fixture('user_2519', 'webapp_337141')

    def url(self, **kwargs):
        kw = {'pk': '337141', 'region': 'cn'}
        kw.update(kwargs)
        return reverse('approve-region', kwargs=kw)

    def test_verbs(self):
        self.grant_permission(self.profile, 'Apps:ReviewRegionCN')
        self._allowed_verbs(self.url(), ['post'])

    def test_anon(self):
        res = self.anon.post(self.url())
        eq_(res.status_code, 403)

    def test_bad_webapp(self):
        self.grant_permission(self.profile, 'Apps:ReviewRegionCN')
        res = self.client.post(self.url(pk='999'))
        eq_(res.status_code, 404)

    def test_webapp_not_pending_in_region(self):
        self.grant_permission(self.profile, 'Apps:ReviewRegionCN')
        res = self.client.post(self.url())
        eq_(res.status_code, 404)

    def test_good_but_no_permission(self):
        res = self.client.post(self.url())
        eq_(res.status_code, 403)

    def test_good_webapp_but_wrong_region_permission(self):
        self.grant_permission(self.profile, 'Apps:ReviewRegionBR')

        app = Webapp.objects.get(id=337141)
        app.geodata.set_status('cn', mkt.STATUS_PENDING, save=True)

        res = self.client.post(self.url())
        eq_(res.status_code, 403)

    def test_good_webapp_but_wrong_region_queue(self):
        self.grant_permission(self.profile, 'Apps:ReviewRegionCN')

        app = Webapp.objects.get(id=337141)
        app.geodata.set_status('cn', mkt.STATUS_PENDING, save=True)

        res = self.client.post(self.url(region='br'))
        eq_(res.status_code, 403)

    def test_good_rejected(self):
        self.grant_permission(self.profile, 'Apps:ReviewRegionCN')

        app = Webapp.objects.get(id=337141)
        app.geodata.set_status('cn', mkt.STATUS_PENDING, save=True)
        app.geodata.set_nominated_date('cn', save=True)

        res = self.client.post(self.url())
        eq_(res.status_code, 200)
        obj = json.loads(res.content)
        eq_(obj['approved'], False)
        eq_(app.geodata.reload().get_status('cn'), mkt.STATUS_REJECTED)

    def test_good_approved(self):
        self.grant_permission(self.profile, 'Apps:ReviewRegionCN')

        app = Webapp.objects.get(id=337141)
        app.geodata.set_status('cn', mkt.STATUS_PENDING, save=True)
        app.geodata.set_nominated_date('cn', save=True)

        res = self.client.post(self.url(), data=json.dumps({'approve': '1'}))
        eq_(res.status_code, 200)
        obj = json.loads(res.content)
        eq_(obj['approved'], True)
        eq_(app.geodata.reload().get_status('cn'), mkt.STATUS_PUBLIC)


class TestGenerateToken(RestOAuth):
    fixtures = fixture('user_2519', 'webapp_337141')

    def setUp(self):
        super(TestGenerateToken, self).setUp()
        self.app = Webapp.objects.get(pk=337141)
        self.url = reverse('generate-reviewer-token', args=[self.app.app_slug])
        self.user = UserProfile.objects.get(pk=2519)
        self.req = RequestFactory().get('/')
        self.req.user = self.user

    def test_verbs(self):
        self._allowed_verbs(self.url, ('post'))

    def test_not_allowed(self):
        eq_(self.anon.post(self.url).status_code, 403)

    def test_still_not_allowed(self):
        eq_(self.client.post(self.url).status_code, 403)

    def test_token(self):
        self.grant_permission(self.user, 'Apps:Review')
        res = self.client.post(self.url)
        eq_(res.status_code, 200, res.content)
        data = json.loads(res.content)
        assert 'token' in data

        # Check data in token.
        assert Token.valid(data['token'], data={'app_id': self.app.id})


class TestUpdateAdditionalReview(RestOAuth):
    fixtures = fixture('user_2519', 'webapp_337141')

    def setUp(self):
        super(TestUpdateAdditionalReview, self).setUp()
        self.grant_permission(self.profile, 'Apps:ReviewTarako')
        self.app = Webapp.objects.get(pk=337141)
        self.review = self.app.additionalreview_set.create(queue='my-queue')
        self.get_object_patcher = mock.patch(
            'mkt.reviewers.views.UpdateAdditionalReviewViewSet.get_object')
        self.get_object = self.get_object_patcher.start()
        self.get_object.return_value = self.review
        self.addCleanup(self.get_object_patcher.stop)

    def patch(self, data, pk=None):
        if pk is None:
            pk = self.review.pk
        return self.client.patch(
            reverse('additionalreview-detail', args=[pk]),
            data=json.dumps(data),
            content_type='application/json')

    def test_review_tarako_required(self):
        self.remove_permission(self.profile, 'Apps:ReviewTarako')
        response = self.patch({'passed': True})
        eq_(response.status_code, 403)

    def test_404_with_invalid_id(self):
        self.get_object_patcher.stop()
        response = self.patch({'passed': True}, pk=self.review.pk + 1)
        eq_(response.status_code, 404)
        self.get_object_patcher.start()

    def test_post_review_task_called_when_passed(self):
        with mock.patch.object(self.review, 'execute_post_review_task') as \
                execute_post_review_task:
            response = self.patch({'passed': True})
            eq_(response.status_code, 200)
            ok_(execute_post_review_task.called)

    def test_post_review_task_called_when_failed(self):
        with mock.patch.object(self.review, 'execute_post_review_task') as \
                execute_post_review_task:
            response = self.patch({'passed': False})
            eq_(response.status_code, 200)
            ok_(execute_post_review_task.called)

    def test_no_changes_without_pass_or_fail(self):
        with mock.patch.object(self.review, 'execute_post_review_task') as \
                execute_post_review_task:
            response = self.patch({})
            eq_(response.status_code, 400)
            eq_(response.json,
                {'non_field_errors': ['passed must be a boolean value']})
            ok_(not execute_post_review_task.called)

    def test_comment_is_not_required(self):
        with mock.patch.object(self.review, 'execute_post_review_task') as \
                execute_post_review_task:
            response = self.patch({'passed': False})
            eq_(response.status_code, 200)
            ok_(execute_post_review_task.called)

    def test_comment_can_be_set(self):
        with mock.patch.object(self.review, 'execute_post_review_task') as \
                execute_post_review_task:
            response = self.patch({'passed': False, 'comment': 'no work'})
            eq_(response.status_code, 200)
            eq_(self.review.reload().comment, 'no work')
            ok_(execute_post_review_task.called)

    def test_reviewer_gets_set_to_current_user(self):
        with mock.patch.object(self.review, 'execute_post_review_task') as \
                execute_post_review_task:
            response = self.patch({'passed': False})
            eq_(response.status_code, 200)
            eq_(self.review.reload().reviewer, self.profile)
            ok_(execute_post_review_task.called)

    def test_review_completed_gets_set(self):
        with mock.patch.object(self.review, 'execute_post_review_task') as \
                execute_post_review_task:
            response = self.patch({'passed': False})
            eq_(response.status_code, 200)
            ok_(self.review.reload().review_completed - datetime.now() <
                timedelta(seconds=1))
            ok_(execute_post_review_task.called)

    def test_review_can_only_happen_once(self):
        self.review.update(passed=True)
        with mock.patch.object(self.review, 'execute_post_review_task') as \
                execute_post_review_task:
            response = self.patch({'passed': False})
            eq_(response.status_code, 400)
            eq_(response.json,
                {'non_field_errors': ['has already been reviewed']})
            ok_(not execute_post_review_task.called)


class TestCreateAdditionalReview(RestOAuth):
    fixtures = fixture('user_2519', 'webapp_337141')

    def setUp(self):
        super(TestCreateAdditionalReview, self).setUp()
        self.app = Webapp.objects.get(pk=337141)
        self.addon_user = self.app.addonuser_set.create(user=self.profile)

    def post(self, data):
        return self.client.post(
            reverse('additionalreviews'),
            data=json.dumps(data),
            content_type='application/json')

    def review_exists(self):
        return (AdditionalReview.objects
                                .filter(queue=QUEUE_TARAKO, app_id=self.app.pk)
                                .exists())

    def test_review_can_be_created(self):
        ok_(not self.review_exists())
        response = self.post({'queue': QUEUE_TARAKO, 'app': self.app.pk})
        eq_(response.status_code, 201)
        ok_(self.review_exists())

    def test_queue_must_be_tarako(self):
        ok_(not self.review_exists())
        response = self.post({'queue': 'not-tarako', 'app': self.app.pk})
        eq_(response.status_code, 400)
        eq_(response.json, {'queue': ['is not a valid choice']})
        ok_(not self.review_exists())

    def test_a_non_author_does_not_have_access(self):
        self.addon_user.delete()
        ok_(not self.review_exists())
        response = self.post({'queue': QUEUE_TARAKO, 'app': self.app.pk})
        eq_(response.status_code, 403)
        ok_(not self.review_exists())

    def test_admin_has_access(self):
        self.grant_permission(self.profile, 'Apps:Edit')
        self.addon_user.delete()
        ok_(not self.review_exists())
        response = self.post({'queue': QUEUE_TARAKO, 'app': self.app.pk})
        eq_(response.status_code, 201)
        ok_(self.review_exists())

    def test_passed_cannot_be_set(self):
        ok_(not self.review_exists())
        response = self.post(
            {'queue': QUEUE_TARAKO, 'app': self.app.pk, 'passed': True})
        eq_(response.status_code, 201)
        ok_(self.review_exists())
        eq_(AdditionalReview.objects.get(app_id=self.app.pk).passed, None)

    def test_only_one_pending_review(self):
        AdditionalReview.objects.create(queue=QUEUE_TARAKO, app=self.app)
        self.app.update(status=mkt.STATUS_PENDING)
        eq_(AdditionalReview.objects.filter(app=self.app).count(), 1)
        response = self.post({'queue': QUEUE_TARAKO, 'app': self.app.pk})
        eq_(response.status_code, 400)
        eq_(response.json, {'app': ['has a pending review']})
        eq_(AdditionalReview.objects.filter(app=self.app).count(), 1)

    def test_unknown_app_is_an_error(self):
        response = self.post({'queue': QUEUE_TARAKO, 'app': 123})
        eq_(response.status_code, 400)
        eq_(response.json,
            {'app': ["Invalid pk '123' - object does not exist."]})


class TestCannedResponseAPI(RestOAuth):
    def setUp(self):
        self.canned = CannedResponse.objects.create(
            name='canned',
            response='This is a canned response.', sort_group='sortme')
        self.url_list = reverse('cannedresponse-list')
        self.url_detail = reverse('cannedresponse-detail',
                                  kwargs={'pk': self.canned.pk})
        self.url_detail_404 = reverse('cannedresponse-detail',
                                      kwargs={'pk': self.canned.pk + 666})
        super(TestCannedResponseAPI, self).setUp()

    def test_norights_list(self):
        res = self.anon.get(self.url_list)
        eq_(res.status_code, 403)
        res = self.client.get(self.url_list)
        eq_(res.status_code, 403)

    def test_norights_get(self):
        res = self.anon.get(self.url_detail)
        eq_(res.status_code, 403)
        res = self.client.get(self.url_detail)
        eq_(res.status_code, 403)

    def test_norights_patch(self):
        res = self.anon.patch(self.url_detail, {
            'name': 'notcanned'
        })
        eq_(res.status_code, 403)
        res = self.client.patch(self.url_detail, {
            'name': 'notcanned'
        })
        eq_(res.status_code, 403)

    def test_norights_put(self):
        res = self.anon.put(self.url_detail, {
            'name': 'notcanned',
            'response': 'This is not a canned response.',
            'sort_group': 'basic'
        })
        eq_(res.status_code, 403)
        res = self.client.put(self.url_detail, {
            'name': 'notcanned',
            'response': 'This is not a canned response.',
            'sort_group': 'basic'
        })
        eq_(res.status_code, 403)

    def test_norights_post(self):
        res = self.anon.post(self.url_list, {
            'name': 'notcanned',
            'response': 'This is not a canned response.',
            'sort_group': 'basic'
        })
        eq_(res.status_code, 403)
        res = self.client.post(self.url_list, {
            'name': 'notcanned',
            'response': 'This is not a canned response.',
            'sort_group': 'basic'
        })
        eq_(res.status_code, 403)

    def test_norights_delete(self):
        res = self.anon.delete(self.url_detail)
        eq_(res.status_code, 403)

    def test_list(self):
        self.grant_permission(self.profile, 'Admin:ReviewerTools')
        res = self.client.get(self.url_list)
        eq_(res.status_code, 200)
        eq_(len(res.json['objects']), 1)

    def test_get(self):
        self.grant_permission(self.profile, 'Admin:ReviewerTools')
        res = self.client.get(self.url_detail)
        eq_(res.status_code, 200)
        eq_(res.json['name'], {'en-US': unicode(self.canned.name)})
        eq_(res.json['response'], {'en-US': unicode(self.canned.response)})
        eq_(res.json['sort_group'], self.canned.sort_group)

    def test_get_404(self):
        self.grant_permission(self.profile, 'Admin:ReviewerTools')
        res = self.client.get(self.url_detail_404)
        eq_(res.status_code, 404)

    def test_post(self):
        self.grant_permission(self.profile, 'Admin:ReviewerTools')
        res = self.client.post(self.url_list, json.dumps({
            'name': {'en-US': 'notcanned', 'fr': u'cânètte'},
            'response': 'This is not a canned response.',
            'sort_group': 'basic'
        }))
        eq_(res.status_code, 201)
        eq_(CannedResponse.objects.count(), 2)
        canned = CannedResponse.objects.get(pk=res.json['id'])
        eq_(res.json['name'], {'en-US': 'notcanned', 'fr': u'cânètte'})
        eq_(res.json['response'], {'en-US': unicode(canned.response)})
        eq_(res.json['sort_group'], canned.sort_group)

    def test_patch(self):
        self.grant_permission(self.profile, 'Admin:ReviewerTools')
        res = self.client.patch(self.url_detail, json.dumps({
            'sort_group': 'coolstorybro'
        }))
        eq_(res.status_code, 200)
        eq_(CannedResponse.objects.count(), 1)
        self.canned.reload()
        eq_(res.json['sort_group'], 'coolstorybro')
        eq_(res.json['sort_group'], self.canned.sort_group)

    def test_put_but_not_everything(self):
        self.grant_permission(self.profile, 'Admin:ReviewerTools')
        res = self.client.put(self.url_detail, json.dumps({
            'sort_group': 'woops'
        }))
        eq_(res.status_code, 400)

    def test_put(self):
        self.grant_permission(self.profile, 'Admin:ReviewerTools')
        res = self.client.put(self.url_detail, json.dumps({
            'name': {'en-US': 'notcanned', 'fr': u'cânètte'},
            'response': 'This is not a canned response.',
            'sort_group': 'basic'
        }))
        eq_(res.status_code, 200)
        eq_(CannedResponse.objects.count(), 1)
        self.canned.reload()
        eq_(res.json['name'], {'en-US': 'notcanned', 'fr': u'cânètte'})
        eq_(res.json['response'], {'en-US': unicode(self.canned.response)})
        eq_(res.json['sort_group'], self.canned.sort_group)

    def test_delete(self):
        self.grant_permission(self.profile, 'Admin:ReviewerTools')
        res = self.client.delete(self.url_detail)
        eq_(res.status_code, 204)
        eq_(CannedResponse.objects.count(), 0)


class TestReviewerScoreAPI(RestOAuth):
    def setUp(self):
        super(TestReviewerScoreAPI, self).setUp()
        self.score = ReviewerScore.objects.create(
            user=self.profile,
            note='This is a note.', score=42, note_key=mkt.REVIEWED_MANUAL)
        self.url_list = reverse('reviewerscore-list')
        self.url_detail = reverse('reviewerscore-detail',
                                  kwargs={'pk': self.score.pk})
        self.url_detail_404 = reverse('reviewerscore-detail',
                                      kwargs={'pk': self.score.pk + 666})

    def test_norights_list(self):
        res = self.anon.get(self.url_list)
        eq_(res.status_code, 403)
        res = self.client.get(self.url_list)
        eq_(res.status_code, 403)

    def test_norights_get(self):
        res = self.anon.get(self.url_detail)
        eq_(res.status_code, 403)
        res = self.client.get(self.url_detail)
        eq_(res.status_code, 403)

    def test_norights_patch(self):
        res = self.anon.patch(self.url_detail, {
            'score': 44
        })
        eq_(res.status_code, 403)
        res = self.client.patch(self.url_detail, {
            'score': 44
        })
        eq_(res.status_code, 403)

    def test_norights_put(self):
        res = self.anon.put(self.url_detail, {
            'score': 44,
            'user': self.profile.pk,
        })
        eq_(res.status_code, 403)
        res = self.client.put(self.url_detail, {
            'score': 44,
            'user': self.profile.pk,
        })
        eq_(res.status_code, 403)

    def test_norights_post(self):
        res = self.anon.post(self.url_list, {
            'score': 44,
            'user': self.profile.pk,
        })
        eq_(res.status_code, 403)
        res = self.client.post(self.url_list, {
            'score': 44,
            'user': self.profile.pk,
        })
        eq_(res.status_code, 403)

    def test_norights_delete(self):
        res = self.anon.delete(self.url_detail)
        eq_(res.status_code, 403)

    def test_list(self):
        # Add an extra instance that shouldn't be returned because of its
        # note_key.
        ReviewerScore.objects.create(
            user=self.profile,
            note='Hide me!', score=43, note_key=mkt.REVIEWED_APP_REVIEW)
        self.grant_permission(self.profile, 'Admin:ReviewerTools')
        res = self.client.get(self.url_list)
        eq_(res.status_code, 200)
        eq_(len(res.json['objects']), 1)
        eq_(res.json['objects'][0]['id'], self.score.id)

    def test_get(self):
        self.grant_permission(self.profile, 'Admin:ReviewerTools')
        res = self.client.get(self.url_detail)
        eq_(res.status_code, 200)
        eq_(res.json['score'], self.score.score)
        eq_(res.json['note'], self.score.note)
        eq_(res.json['user'], self.score.user.pk)

    def test_get_404(self):
        self.grant_permission(self.profile, 'Admin:ReviewerTools')
        res = self.client.get(self.url_detail_404)
        eq_(res.status_code, 404)

    def test_get_404_note_key(self):
        self.grant_permission(self.profile, 'Admin:ReviewerTools')
        # Add an extra instance that shouldn't be returned because of its
        # note_key.
        score = ReviewerScore.objects.create(
            user=self.profile,
            note='Hide me!', score=43, note_key=mkt.REVIEWED_APP_REVIEW)
        url_detail = reverse('reviewerscore-detail',
                             kwargs={'pk': score.pk})
        res = self.client.get(url_detail)
        eq_(res.status_code, 404)

    def test_post(self):
        self.grant_permission(self.profile, 'Admin:ReviewerTools')
        res = self.client.post(self.url_list, json.dumps({
            'score': 45,
            'note': 'This is a simple note',
            'user': self.profile.pk
        }))
        eq_(res.status_code, 201)
        eq_(ReviewerScore.objects.count(), 2)
        score = ReviewerScore.objects.get(pk=res.json['id'])
        eq_(res.json['score'], 45)
        eq_(res.json['note'], 'This is a simple note')
        eq_(res.json['user'], self.profile.pk)
        eq_(res.json['score'], score.score)
        eq_(res.json['note'], score.note)
        eq_(res.json['user'], score.user.pk)
        eq_(score.note_key, mkt.REVIEWED_MANUAL)

    def test_post_no_note(self):
        self.grant_permission(self.profile, 'Admin:ReviewerTools')
        res = self.client.post(self.url_list, json.dumps({
            'score': 48,
            'user': self.profile.pk
        }))
        eq_(res.status_code, 201)
        eq_(ReviewerScore.objects.count(), 2)
        score = ReviewerScore.objects.get(pk=res.json['id'])
        eq_(res.json['note'], '')
        eq_(res.json['note'], score.note)

    def test_post_but_not_everything(self):
        self.grant_permission(self.profile, 'Admin:ReviewerTools')
        res = self.client.post(self.url_list, json.dumps({
            'score': 47
        }))
        eq_(res.status_code, 400)
        ok_('user' in res.json)

    def test_post_but_invalid_user(self):
        self.grant_permission(self.profile, 'Admin:ReviewerTools')
        res = self.client.post(self.url_list, json.dumps({
            'score': 49,
            'user': self.profile.pk + 666
        }))
        eq_(res.status_code, 400)
        ok_('user' in res.json)

    def test_patch(self):
        self.grant_permission(self.profile, 'Admin:ReviewerTools')
        res = self.client.patch(self.url_detail, json.dumps({
            'score': 46
        }))
        eq_(res.status_code, 200)
        eq_(ReviewerScore.objects.count(), 1)
        self.score.reload()
        eq_(res.json['score'], 46)
        eq_(res.json['score'], self.score.score)
        # Note has not been touched.
        eq_(res.json['note'], 'This is a note.')
        eq_(res.json['note'], self.score.note)

    def test_patch_blank_note(self):
        self.grant_permission(self.profile, 'Admin:ReviewerTools')
        res = self.client.patch(self.url_detail, json.dumps({
            'note': ''
        }))
        eq_(res.status_code, 200)
        eq_(ReviewerScore.objects.count(), 1)
        self.score.reload()
        # Score has not been touched.
        eq_(res.json['score'], 42)
        eq_(res.json['score'], self.score.score)
        # We set a blank note.
        eq_(res.json['note'], '')
        eq_(res.json['note'], self.score.note)

    def test_patch_note_key_is_ignored(self):
        self.grant_permission(self.profile, 'Admin:ReviewerTools')
        res = self.client.patch(self.url_detail, json.dumps({
            'score': 46,
            'note_key': mkt.REVIEWED_APP_REVIEW
        }))
        eq_(res.status_code, 200)
        eq_(ReviewerScore.objects.count(), 1)
        self.score.reload()
        eq_(res.json['score'], 46)
        eq_(res.json['score'], self.score.score)
        eq_(self.score.note_key, mkt.REVIEWED_MANUAL)

    def test_put_but_not_everything(self):
        self.grant_permission(self.profile, 'Admin:ReviewerTools')
        res = self.client.put(self.url_detail, json.dumps({
            'note': 'lol'
        }))
        eq_(res.status_code, 400)
        ok_('user' in res.json)
        ok_('score' in res.json)

    def test_put(self):
        self.grant_permission(self.profile, 'Admin:ReviewerTools')
        res = self.client.put(self.url_detail, json.dumps({
            'score': 51,
            'user': self.profile.pk
        }))
        eq_(res.status_code, 200)
        eq_(ReviewerScore.objects.count(), 1)
        self.score.reload()
        eq_(res.json['score'], 51)
        eq_(res.json['note'], '')
        eq_(res.json['user'], self.profile.pk)
        eq_(res.json['score'], self.score.score)
        eq_(res.json['note'], self.score.note)
        eq_(res.json['user'], self.score.user.pk)

    def test_delete(self):
        self.grant_permission(self.profile, 'Admin:ReviewerTools')
        res = self.client.delete(self.url_detail)
        eq_(res.status_code, 204)
        eq_(ReviewerScore.objects.count(), 0)


class TestReviewerActions(RestOAuth):
    fixtures = fixture('user_2519', 'webapp_337141')

    def setUp(self):
        super(TestReviewerActions, self).setUp()
        self.app = Webapp.objects.get(pk=337141)
        self.comment = "test comment"
        self.user = UserProfile.objects.get(pk=2519)
        self.grant_permission(self.user, 'Apps:Review')

    def postit(self, view):
        url = reverse('app-' + view, kwargs={'pk': '337141'})
        return self.client.post(url, json.dumps(
            {'comments': self.comment}))

    def check_note(self):
        note = self.app.threads.get().notes.get()
        eq_(note.body, self.comment)

    def test_approve(self):
        self.app.status = mkt.STATUS_PENDING
        res = self.postit('approve')
        eq_(res.status_code, 200)
        eq_(res.json['score'], 60)
        eq_(self.app.reload().status, mkt.STATUS_PUBLIC)
        self.check_note()

    def test_reject(self):
        self.app.status = mkt.STATUS_PENDING
        res = self.postit('reject')
        eq_(res.status_code, 200)
        eq_(self.app.reload().status, mkt.STATUS_REJECTED)
        self.check_note()

    def test_request_info(self):
        self.app.status = mkt.STATUS_PENDING
        res = self.postit('info')
        eq_(res.status_code, 200)
        ok_(self.app.latest_version.reload().has_info_request)
        self.check_note()

    def test_escalate(self):
        self.app.status = mkt.STATUS_PENDING
        res = self.postit('escalate')
        eq_(res.status_code, 200)
        ok_(EscalationQueue.objects.filter(addon=self.app).exists())
        self.check_note()

    def test_clear_escalation(self):
        self.grant_permission(self.user, 'Apps:Edit')
        self.app.status = mkt.STATUS_PENDING
        EscalationQueue.objects.create(addon=self.app)
        url = reverse('app-escalate', kwargs={'pk': '337141'})
        res = self.client.delete(url, {'comments': self.comment})
        eq_(res.status_code, 200)
        ok_(not EscalationQueue.objects.filter(addon=self.app).exists())
        self.check_note()

    def test_disable(self):
        self.grant_permission(self.user, 'Apps:Edit')
        self.app.status = mkt.STATUS_PENDING
        res = self.postit('disable')
        eq_(res.status_code, 200)
        eq_(self.app.reload().status, mkt.STATUS_DISABLED)
        self.check_note()

    def test_rereview(self):
        self.app.status = mkt.STATUS_PENDING
        RereviewQueue.objects.create(addon=self.app)
        url = reverse('app-rereview', kwargs={'pk': '337141'})
        res = self.client.delete(url, {'comments': self.comment})
        eq_(res.status_code, 200)
        ok_(not RereviewQueue.objects.filter(addon=self.app).exists())
        self.check_note()

    def test_comment(self):
        self.app.status = mkt.STATUS_PENDING
        res = self.postit('comment')
        eq_(res.status_code, 200)
        ok_(self.app.latest_version.reload().has_editor_comment, True)
        self.check_note()
