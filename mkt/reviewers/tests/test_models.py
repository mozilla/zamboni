# -*- coding: utf-8 -*-
import time

import mock
from nose.tools import eq_

import mkt
import mkt.site.tests

from mkt.constants import comm
from mkt.reviewers.models import EscalationQueue, RereviewQueue, ReviewerScore
from mkt.site.tests import app_factory, user_factory
from mkt.users.models import UserProfile
from mkt.webapps.models import AddonDeviceType
from mkt.websites.utils import website_factory


class TestReviewerScore(mkt.site.tests.TestCase):

    def setUp(self):
        self.app = app_factory(status=mkt.STATUS_PENDING)
        self.website = website_factory()
        self.user = user_factory(email='editor')
        self.grant_permission(self.user, 'Apps:Review')
        self.admin_user = user_factory(email='admin')
        self.grant_permission(self.admin_user, '*:*', name='Admins')
        user_factory(email='regular')

    def _give_points(self, user=None, app=None, status=None):
        user = user or self.user
        app = app or self.app
        ReviewerScore.award_points(user, app, status or app.status)

    def check_event(self, status, event, **kwargs):
        eq_(ReviewerScore.get_event(self.app, status, **kwargs), event, (
            'Score event status:%s was not %s' % (status, event)))

    def test_events_webapps(self):
        self.app = app_factory()
        self.check_event(mkt.STATUS_PENDING,
                         mkt.REVIEWED_WEBAPP_HOSTED)

        RereviewQueue.objects.create(addon=self.app)
        self.check_event(mkt.STATUS_PUBLIC,
                         mkt.REVIEWED_WEBAPP_REREVIEW, in_rereview=True)
        self.check_event(mkt.STATUS_UNLISTED,
                         mkt.REVIEWED_WEBAPP_REREVIEW, in_rereview=True)
        self.check_event(mkt.STATUS_APPROVED,
                         mkt.REVIEWED_WEBAPP_REREVIEW, in_rereview=True)
        RereviewQueue.objects.all().delete()

        self.app.is_packaged = True
        self.check_event(mkt.STATUS_PENDING,
                         mkt.REVIEWED_WEBAPP_PACKAGED)
        self.check_event(mkt.STATUS_PUBLIC,
                         mkt.REVIEWED_WEBAPP_UPDATE)
        self.check_event(mkt.STATUS_UNLISTED,
                         mkt.REVIEWED_WEBAPP_UPDATE)
        self.check_event(mkt.STATUS_APPROVED,
                         mkt.REVIEWED_WEBAPP_UPDATE)

        self.app.latest_version.is_privileged = True
        self.check_event(mkt.STATUS_PENDING,
                         mkt.REVIEWED_WEBAPP_PRIVILEGED)
        self.check_event(mkt.STATUS_PUBLIC,
                         mkt.REVIEWED_WEBAPP_PRIVILEGED_UPDATE)
        self.check_event(mkt.STATUS_UNLISTED,
                         mkt.REVIEWED_WEBAPP_PRIVILEGED_UPDATE)
        self.check_event(mkt.STATUS_APPROVED,
                         mkt.REVIEWED_WEBAPP_PRIVILEGED_UPDATE)

    def test_award_points(self):
        self._give_points()
        eq_(ReviewerScore.objects.all()[0].score,
            mkt.REVIEWED_SCORES[mkt.REVIEWED_WEBAPP_HOSTED])

    def test_award_moderation_points(self):
        ReviewerScore.award_moderation_points(self.user, self.app, 1)
        score = ReviewerScore.objects.all()[0]
        eq_(score.score, mkt.REVIEWED_SCORES.get(mkt.REVIEWED_APP_REVIEW))
        eq_(score.note_key, mkt.REVIEWED_APP_REVIEW)

        ReviewerScore.award_moderation_points(self.user, self.app, 1,
                                              undo=True)
        score = ReviewerScore.objects.all()[1]
        eq_(score.score, mkt.REVIEWED_SCORES.get(mkt.REVIEWED_APP_REVIEW_UNDO))
        eq_(score.note_key, mkt.REVIEWED_APP_REVIEW_UNDO)

        # If we change the _UNDO score to be different this test will fail.
        eq_(ReviewerScore.get_total(self.user), 0)

    def test_extra_platform_points(self):
        AddonDeviceType.objects.create(addon=self.app, device_type=1)
        self._give_points()
        score1 = mkt.REVIEWED_SCORES[mkt.REVIEWED_WEBAPP_HOSTED]
        eq_(ReviewerScore.objects.order_by('-pk').first().score, score1)

        AddonDeviceType.objects.create(addon=self.app, device_type=2)
        self._give_points()
        score2 = (mkt.REVIEWED_SCORES[mkt.REVIEWED_WEBAPP_HOSTED] +
                  mkt.REVIEWED_SCORES[mkt.REVIEWED_WEBAPP_PLATFORM_EXTRA])
        eq_(ReviewerScore.objects.order_by('-pk').first().score, score2)

        AddonDeviceType.objects.create(addon=self.app, device_type=3)
        self._give_points()
        score3 = (mkt.REVIEWED_SCORES[mkt.REVIEWED_WEBAPP_HOSTED] +
                  mkt.REVIEWED_SCORES[mkt.REVIEWED_WEBAPP_PLATFORM_EXTRA] * 2)
        eq_(ReviewerScore.objects.order_by('-pk').first().score, score3)

    def test_award_mark_abuse_points_app(self):
        ReviewerScore.award_mark_abuse_points(self.user, addon=self.app)
        score = ReviewerScore.objects.all()[0]
        eq_(score.score, mkt.REVIEWED_SCORES.get(
            mkt.REVIEWED_APP_ABUSE_REPORT))
        eq_(score.note_key, mkt.REVIEWED_APP_ABUSE_REPORT)

    def test_award_mark_abuse_points_website(self):
        ReviewerScore.award_mark_abuse_points(self.user, website=self.website)
        score = ReviewerScore.objects.all()[0]
        eq_(score.score, mkt.REVIEWED_SCORES.get(
            mkt.REVIEWED_WEBSITE_ABUSE_REPORT))
        eq_(score.note_key, mkt.REVIEWED_WEBSITE_ABUSE_REPORT)

    def test_get_total(self):
        user2 = UserProfile.objects.get(email='admin@mozilla.com')
        self._give_points()
        self._give_points()
        self._give_points(user=user2)
        eq_(ReviewerScore.get_total(self.user),
            mkt.REVIEWED_SCORES[mkt.REVIEWED_WEBAPP_HOSTED] * 2)
        eq_(ReviewerScore.get_total(user2),
            mkt.REVIEWED_SCORES[mkt.REVIEWED_WEBAPP_HOSTED])

    def test_get_recent(self):
        user2 = UserProfile.objects.get(email='admin@mozilla.com')
        self._give_points()
        time.sleep(1)  # Wait 1 sec so ordering by created is checked.
        self._give_points()
        self._give_points(user=user2)
        scores = ReviewerScore.get_recent(self.user)
        eq_(len(scores), 2)
        eq_(scores[0].score, mkt.REVIEWED_SCORES[mkt.REVIEWED_WEBAPP_HOSTED])
        eq_(scores[1].score, mkt.REVIEWED_SCORES[mkt.REVIEWED_WEBAPP_HOSTED])

    def test_get_leaderboards(self):
        user2 = UserProfile.objects.get(email='regular@mozilla.com')
        self._give_points()
        self._give_points()
        self._give_points(user=user2)
        leaders = ReviewerScore.get_leaderboards(self.user)
        eq_(leaders['user_rank'], 1)
        eq_(leaders['leader_near'], [])
        eq_(leaders['leader_top'][0]['rank'], 1)
        eq_(leaders['leader_top'][0]['user_id'], self.user.id)
        eq_(leaders['leader_top'][0]['total'],
            mkt.REVIEWED_SCORES[mkt.REVIEWED_WEBAPP_HOSTED] +
            mkt.REVIEWED_SCORES[mkt.REVIEWED_WEBAPP_HOSTED])
        eq_(leaders['leader_top'][1]['rank'], 2)
        eq_(leaders['leader_top'][1]['user_id'], user2.id)
        eq_(leaders['leader_top'][1]['total'],
            mkt.REVIEWED_SCORES[mkt.REVIEWED_WEBAPP_HOSTED])

    def test_no_admins_or_staff_in_leaderboards(self):
        user2 = UserProfile.objects.get(email='admin@mozilla.com')
        self._give_points()
        self._give_points(user=user2)
        leaders = ReviewerScore.get_leaderboards(self.user)
        eq_(leaders['user_rank'], 1)
        eq_(leaders['leader_near'], [])
        eq_(leaders['leader_top'][0]['user_id'], self.user.id)
        eq_(len(leaders['leader_top']), 1)  # Only the editor is here.
        assert user2.id not in [l['user_id'] for l in leaders['leader_top']], (
            'Unexpected admin user found in leaderboards.')

    def test_get_performance(self):
        self._give_points()
        ReviewerScore.award_moderation_points(self.user, self.app, 1)
        performance = ReviewerScore.get_performance(self.user)
        eq_(len(performance), 1)

    def test_get_performance_since(self):
        self._give_points()
        ReviewerScore.award_moderation_points(self.user, self.app, 1)
        rs = list(ReviewerScore.objects.all())
        rs[0].update(created=self.days_ago(50))
        performance = ReviewerScore.get_performance_since(self.user,
                                                          self.days_ago(30))
        eq_(len(performance), 1)

    def test_get_leaderboards_last(self):
        users = []
        for i in range(6):
            users.append(user_factory())
        last_user = users.pop(len(users) - 1)
        for u in users:
            self._give_points(user=u)
        # Last user gets lower points by a moderation review.
        ReviewerScore.award_moderation_points(last_user, self.app, 1)
        leaders = ReviewerScore.get_leaderboards(last_user)
        eq_(leaders['user_rank'], 6)
        eq_(len(leaders['leader_top']), 3)
        eq_(len(leaders['leader_near']), 2)

    def test_all_users_by_score(self):
        user2 = UserProfile.objects.get(email='regular@mozilla.com')
        mkt.REVIEWED_LEVELS[0]['points'] = 120
        self._give_points()
        self._give_points()
        self._give_points(user=user2)
        users = ReviewerScore.all_users_by_score()
        eq_(len(users), 2)
        # First user.
        eq_(users[0]['total'], 120)
        eq_(users[0]['user_id'], self.user.id)
        eq_(users[0]['level'], mkt.REVIEWED_LEVELS[0]['name'])
        # Second user.
        eq_(users[1]['total'], 60)
        eq_(users[1]['user_id'], user2.id)
        eq_(users[1]['level'], '')

    def test_caching(self):
        self._give_points()

        with self.assertNumQueries(1):
            ReviewerScore.get_total(self.user)
        with self.assertNumQueries(0):
            ReviewerScore.get_total(self.user)

        with self.assertNumQueries(1):
            ReviewerScore.get_recent(self.user)
        with self.assertNumQueries(0):
            ReviewerScore.get_recent(self.user)

        with self.assertNumQueries(1):
            ReviewerScore.get_leaderboards(self.user)
        with self.assertNumQueries(0):
            ReviewerScore.get_leaderboards(self.user)

        with self.assertNumQueries(1):
            ReviewerScore.get_performance(self.user)
        with self.assertNumQueries(0):
            ReviewerScore.get_performance(self.user)

        # New points invalidates all caches.
        self._give_points()

        with self.assertNumQueries(1):
            ReviewerScore.get_total(self.user)
        with self.assertNumQueries(1):
            ReviewerScore.get_recent(self.user)
        with self.assertNumQueries(1):
            ReviewerScore.get_leaderboards(self.user)
        with self.assertNumQueries(1):
            ReviewerScore.get_performance(self.user)


class TestRereviewQueue(mkt.site.tests.TestCase):
    def setUp(self):
        self.app = mkt.site.tests.app_factory()

    def test_flag_creates_notes(self):
        RereviewQueue.flag(self.app, mkt.LOG.REREVIEW_PREMIUM_TYPE_UPGRADE)
        eq_(self.app.threads.all()[0].notes.all()[0].note_type,
            comm.REREVIEW_PREMIUM_TYPE_UPGRADE)

    @mock.patch('mkt.search.indexers.BaseIndexer.index_ids')
    def test_signals(self, mock):
        RereviewQueue.flag(self.app, mkt.LOG.REREVIEW_PREMIUM_TYPE_UPGRADE)
        assert mock.called
        mock.reset()
        RereviewQueue.objects.filter(addon=self.app).delete()
        assert mock.called


class TestEscalationQueue(mkt.site.tests.TestCase):
    def setUp(self):
        self.app = mkt.site.tests.app_factory()

    @mock.patch('mkt.search.indexers.BaseIndexer.index_ids')
    def test_signals(self, mock):
        EscalationQueue.objects.create(addon=self.app)
        assert mock.called
        mock.reset()
        EscalationQueue.objects.filter(addon=self.app).delete()
        assert mock.called
