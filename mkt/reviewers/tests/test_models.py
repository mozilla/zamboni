# -*- coding: utf8 -*-
import time
from datetime import datetime, timedelta

import mock
from nose.tools import eq_, ok_

import amo
import amo.tests
from mkt.reviewers.models import (AdditionalReview, RereviewQueue,
                                  ReviewerScore, QUEUE_TARAKO, tarako_passed,
                                  tarako_failed)
from mkt.site.fixtures import fixture
from mkt.tags.models import Tag
from mkt.users.models import UserProfile
from mkt.webapps.models import Webapp


class TestReviewerScore(amo.tests.TestCase):
    fixtures = fixture('group_admin', 'group_editor', 'user_admin',
                       'user_admin_group', 'user_editor', 'user_editor_group',
                       'user_999')

    def setUp(self):
        self.app = amo.tests.app_factory(status=amo.STATUS_PENDING)
        self.user = UserProfile.objects.get(email='editor@mozilla.com')

    def _give_points(self, user=None, app=None, status=None):
        user = user or self.user
        app = app or self.app
        ReviewerScore.award_points(user, app, status or app.status)

    def check_event(self, type, status, event, **kwargs):
        self.app.type = type
        eq_(ReviewerScore.get_event(self.app, status, **kwargs), event, (
            'Score event for type:%s and status:%s was not %s' % (
                type, status, event)))

    def test_events_webapps(self):
        self.app = amo.tests.app_factory()
        self.check_event(self.app.type, amo.STATUS_PENDING,
                         amo.REVIEWED_WEBAPP_HOSTED)

        RereviewQueue.objects.create(addon=self.app)
        self.check_event(self.app.type, amo.STATUS_PUBLIC,
                         amo.REVIEWED_WEBAPP_REREVIEW, in_rereview=True)
        RereviewQueue.objects.all().delete()

        self.app.is_packaged = True
        self.check_event(self.app.type, amo.STATUS_PENDING,
                         amo.REVIEWED_WEBAPP_PACKAGED)
        self.check_event(self.app.type, amo.STATUS_PUBLIC,
                         amo.REVIEWED_WEBAPP_UPDATE)

    def test_award_points(self):
        self._give_points()
        eq_(ReviewerScore.objects.all()[0].score,
            amo.REVIEWED_SCORES[amo.REVIEWED_WEBAPP_HOSTED])

    def test_award_moderation_points(self):
        ReviewerScore.award_moderation_points(self.user, self.app, 1)
        score = ReviewerScore.objects.all()[0]
        eq_(score.score, amo.REVIEWED_SCORES.get(amo.REVIEWED_APP_REVIEW))
        eq_(score.note_key, amo.REVIEWED_APP_REVIEW)

    def test_get_total(self):
        user2 = UserProfile.objects.get(email='admin@mozilla.com')
        self._give_points()
        self._give_points()
        self._give_points(user=user2)
        eq_(ReviewerScore.get_total(self.user),
            amo.REVIEWED_SCORES[amo.REVIEWED_WEBAPP_HOSTED] * 2)
        eq_(ReviewerScore.get_total(user2),
            amo.REVIEWED_SCORES[amo.REVIEWED_WEBAPP_HOSTED])

    def test_get_recent(self):
        user2 = UserProfile.objects.get(email='admin@mozilla.com')
        self._give_points()
        time.sleep(1)  # Wait 1 sec so ordering by created is checked.
        self._give_points()
        self._give_points(user=user2)
        scores = ReviewerScore.get_recent(self.user)
        eq_(len(scores), 2)
        eq_(scores[0].score, amo.REVIEWED_SCORES[amo.REVIEWED_WEBAPP_HOSTED])
        eq_(scores[1].score, amo.REVIEWED_SCORES[amo.REVIEWED_WEBAPP_HOSTED])

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
            amo.REVIEWED_SCORES[amo.REVIEWED_WEBAPP_HOSTED] +
            amo.REVIEWED_SCORES[amo.REVIEWED_WEBAPP_HOSTED])
        eq_(leaders['leader_top'][1]['rank'], 2)
        eq_(leaders['leader_top'][1]['user_id'], user2.id)
        eq_(leaders['leader_top'][1]['total'],
            amo.REVIEWED_SCORES[amo.REVIEWED_WEBAPP_HOSTED])

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

    def test_get_breakdown(self):
        self._give_points()
        ReviewerScore.award_moderation_points(self.user, self.app, 1)
        breakdown = ReviewerScore.get_breakdown(self.user)
        eq_(len(breakdown), 1)
        eq_(set([b.atype for b in breakdown]),
            set([amo.ADDON_WEBAPP]))

    def test_get_breakdown_since(self):
        self._give_points()
        ReviewerScore.award_moderation_points(self.user, self.app, 1)
        rs = list(ReviewerScore.objects.all())
        rs[0].update(created=self.days_ago(50))
        breakdown = ReviewerScore.get_breakdown_since(self.user,
                                                      self.days_ago(30))
        eq_(len(breakdown), 1)
        eq_([b.atype for b in breakdown], [rs[1].addon.type])

    def test_get_leaderboards_last(self):
        users = []
        for i in range(6):
            users.append(UserProfile.objects.create(username='user-%s' % i))
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
        amo.REVIEWED_LEVELS[0]['points'] = 120
        self._give_points()
        self._give_points()
        self._give_points(user=user2)
        users = ReviewerScore.all_users_by_score()
        eq_(len(users), 2)
        # First user.
        eq_(users[0]['total'], 120)
        eq_(users[0]['user_id'], self.user.id)
        eq_(users[0]['level'], amo.REVIEWED_LEVELS[0]['name'])
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
            ReviewerScore.get_breakdown(self.user)
        with self.assertNumQueries(0):
            ReviewerScore.get_breakdown(self.user)

        # New points invalidates all caches.
        self._give_points()

        with self.assertNumQueries(1):
            ReviewerScore.get_total(self.user)
        with self.assertNumQueries(1):
            ReviewerScore.get_recent(self.user)
        with self.assertNumQueries(1):
            ReviewerScore.get_leaderboards(self.user)
        with self.assertNumQueries(1):
            ReviewerScore.get_breakdown(self.user)


class TestAdditionalReview(amo.tests.TestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        self.app = Webapp.objects.get(pk=337141)
        self.review = AdditionalReview.objects.create(
            app=self.app, queue=QUEUE_TARAKO)
        passed_patcher = mock.patch('mkt.reviewers.models.tarako_passed')
        self.tarako_passed = passed_patcher.start()
        self.addCleanup(passed_patcher.stop)
        failed_patcher = mock.patch('mkt.reviewers.models.tarako_failed')
        self.tarako_failed = failed_patcher.start()
        self.addCleanup(failed_patcher.stop)

    def test_review_passed_sets_passed(self):
        eq_(self.review.passed, None, 'expected passed to be None')
        self.review.review_passed()
        eq_(self.review.reload().passed, True, 'expected passed to be True')

    def test_review_passed_sets_review_completed(self):
        eq_(self.review.review_completed, None,
            'expected review_completed to be None')
        self.review.review_passed()
        review_completed = self.review.reload().review_completed
        ok_(review_completed - datetime.now() < timedelta(seconds=1),
            'expected review_completed to be close to now')

    def test_review_passed_calls_tarako_passed(self):
        ok_(not self.tarako_passed.called,
            'expected tarako_passed to be not called')
        self.review.review_passed()
        self.tarako_passed.assert_called_with(self.review)

    def test_review_failed_sets_passed(self):
        eq_(self.review.passed, None, 'expected passed to be None')
        self.review.review_failed()
        eq_(self.review.reload().passed, False, 'expected passed to be False')

    def test_review_failed_sets_review_completed(self):
        eq_(self.review.review_completed, None,
            'expected review_completed to be None')
        self.review.review_failed()
        review_completed = self.review.reload().review_completed
        ok_(review_completed - datetime.now() < timedelta(seconds=1),
            'expected review_completed to be close to now')

    def test_review_failed_calls_tarako_failed(self):
        ok_(not self.tarako_failed.called,
            'expected tarako_failed to be not called')
        self.review.review_failed()
        self.tarako_failed.assert_called_with(self.review)


class TestTarakoFunctions(amo.tests.TestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        self.app = Webapp.objects.get(pk=337141)
        self.review = AdditionalReview.objects.create(
            app=self.app, queue=QUEUE_TARAKO)
        self.tag, _ = Tag.objects.get_or_create(tag_text='tarako')
        index_patcher = mock.patch(
            'mkt.reviewers.models.WebappIndexer.index_ids')
        self.index = index_patcher.start()
        self.addCleanup(index_patcher.stop)

    def tag_exists(self):
        return (self.tag.addons.filter(addon_tags__addon_id=self.app.id)
                               .exists())

    def test_tarako_passed_adds_tarako_tag(self):
        ok_(not self.tag_exists(), 'expected no tarako tag')
        tarako_passed(self.review)
        ok_(self.tag_exists(), 'expected the tarako tag')

    def test_tarako_passed_reindexes_the_app(self):
        ok_(not self.index.called)
        tarako_passed(self.review)
        self.index.assert_called_with([self.app.pk])

    def test_tarako_failed_removed_tarako_tag(self):
        self.tag.save_tag(self.app)
        ok_(self.tag_exists(), 'expected the tarako tag')
        tarako_failed(self.review)
        ok_(not self.tag_exists(), 'expected no tarako tag')

    def test_tarako_failed_reindexes_the_app(self):
        ok_(not self.index.called)
        tarako_failed(self.review)
        self.index.assert_called_with([self.app.pk])
