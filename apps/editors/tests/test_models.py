# -*- coding: utf8 -*-
import time

from nose.tools import eq_

import amo
import amo.tests
from editors.models import RereviewQueue, ReviewerScore
from users.models import UserProfile


class TestReviewerScore(amo.tests.TestCase):
    fixtures = ['base/users']

    def setUp(self):
        self.addon = amo.tests.addon_factory(status=amo.STATUS_NOMINATED)
        self.app = amo.tests.app_factory(status=amo.STATUS_NOMINATED)
        self.user = UserProfile.objects.get(email='editor@mozilla.com')

    def _give_points(self, user=None, addon=None, status=None):
        user = user or self.user
        addon = addon or self.addon
        ReviewerScore.award_points(user, addon, status or addon.status)

    def check_event(self, type, status, event, **kwargs):
        self.addon.type = type
        eq_(ReviewerScore.get_event(self.addon, status, **kwargs), event, (
            'Score event for type:%s and status:%s was not %s' % (
                type, status, event)))

    def test_events_addons(self):
        types = {
            amo.ADDON_ANY: None,
            amo.ADDON_EXTENSION: 'ADDON',
            amo.ADDON_THEME: 'THEME',
            amo.ADDON_DICT: 'DICT',
            amo.ADDON_SEARCH: 'SEARCH',
            amo.ADDON_LPAPP: 'LP',
            amo.ADDON_LPADDON: 'LP',
            amo.ADDON_PLUGIN: 'ADDON',
            amo.ADDON_API: 'ADDON',
            amo.ADDON_PERSONA: 'PERSONA',
            # WEBAPP is special cased below.
        }
        statuses = {
            amo.STATUS_NULL: None,
            amo.STATUS_UNREVIEWED: 'PRELIM',
            amo.STATUS_PENDING: None,
            amo.STATUS_NOMINATED: 'FULL',
            amo.STATUS_PUBLIC: 'UPDATE',
            amo.STATUS_DISABLED: None,
            amo.STATUS_BETA: None,
            amo.STATUS_LITE: 'PRELIM',
            amo.STATUS_LITE_AND_NOMINATED: 'FULL',
            amo.STATUS_PURGATORY: None,
            amo.STATUS_DELETED: None,
            amo.STATUS_REJECTED: None,
            amo.STATUS_PUBLIC_WAITING: None,
            amo.STATUS_REVIEW_PENDING: None,
            amo.STATUS_BLOCKED: None,
        }
        for tk, tv in types.items():
            for sk, sv in statuses.items():
                try:
                    event = getattr(amo, 'REVIEWED_%s_%s' % (tv, sv))
                except AttributeError:
                    try:
                        event = getattr(amo, 'REVIEWED_%s' % tv)
                    except AttributeError:
                        event = None
                self.check_event(tk, sk, event)

    def test_events_webapps(self):
        self.addon = amo.tests.app_factory()
        self.check_event(self.addon.type, amo.STATUS_PENDING,
                         amo.REVIEWED_WEBAPP_HOSTED)

        RereviewQueue.objects.create(addon=self.addon)
        self.check_event(self.addon.type, amo.STATUS_PUBLIC,
                         amo.REVIEWED_WEBAPP_REREVIEW, in_rereview=True)
        RereviewQueue.objects.all().delete()

        self.addon.is_packaged = True
        self.check_event(self.addon.type, amo.STATUS_PENDING,
                         amo.REVIEWED_WEBAPP_PACKAGED)
        self.check_event(self.addon.type, amo.STATUS_PUBLIC,
                         amo.REVIEWED_WEBAPP_UPDATE)

    def test_award_points(self):
        self._give_points()
        eq_(ReviewerScore.objects.all()[0].score,
            amo.REVIEWED_SCORES[amo.REVIEWED_ADDON_FULL])

    def test_award_moderation_points(self):
        ReviewerScore.award_moderation_points(self.user, self.addon, 1)
        score = ReviewerScore.objects.all()[0]
        eq_(score.score, amo.REVIEWED_SCORES.get(amo.REVIEWED_ADDON_REVIEW))
        eq_(score.note_key, amo.REVIEWED_ADDON_REVIEW)

    def test_get_total(self):
        user2 = UserProfile.objects.get(email='admin@mozilla.com')
        self._give_points()
        self._give_points(status=amo.STATUS_LITE)
        self._give_points(user=user2, status=amo.STATUS_NOMINATED)
        eq_(ReviewerScore.get_total(self.user),
            amo.REVIEWED_SCORES[amo.REVIEWED_ADDON_FULL] +
            amo.REVIEWED_SCORES[amo.REVIEWED_ADDON_PRELIM])
        eq_(ReviewerScore.get_total(user2),
            amo.REVIEWED_SCORES[amo.REVIEWED_ADDON_FULL])

    def test_get_recent(self):
        user2 = UserProfile.objects.get(email='admin@mozilla.com')
        self._give_points()
        time.sleep(1)  # Wait 1 sec so ordering by created is checked.
        self._give_points(status=amo.STATUS_LITE)
        self._give_points(user=user2)
        scores = ReviewerScore.get_recent(self.user)
        eq_(len(scores), 2)
        eq_(scores[0].score, amo.REVIEWED_SCORES[amo.REVIEWED_ADDON_PRELIM])
        eq_(scores[1].score, amo.REVIEWED_SCORES[amo.REVIEWED_ADDON_FULL])

    def test_get_leaderboards(self):
        user2 = UserProfile.objects.get(email='regular@mozilla.com')
        self._give_points()
        self._give_points(status=amo.STATUS_LITE)
        self._give_points(user=user2, status=amo.STATUS_NOMINATED)
        leaders = ReviewerScore.get_leaderboards(self.user)
        eq_(leaders['user_rank'], 1)
        eq_(leaders['leader_near'], [])
        eq_(leaders['leader_top'][0]['rank'], 1)
        eq_(leaders['leader_top'][0]['user_id'], self.user.id)
        eq_(leaders['leader_top'][0]['total'],
            amo.REVIEWED_SCORES[amo.REVIEWED_ADDON_FULL] +
            amo.REVIEWED_SCORES[amo.REVIEWED_ADDON_PRELIM])
        eq_(leaders['leader_top'][1]['rank'], 2)
        eq_(leaders['leader_top'][1]['user_id'], user2.id)
        eq_(leaders['leader_top'][1]['total'],
            amo.REVIEWED_SCORES[amo.REVIEWED_ADDON_FULL])

        self._give_points(
            user=user2, addon=amo.tests.addon_factory(type=amo.ADDON_PERSONA))
        leaders = ReviewerScore.get_leaderboards(
            self.user, addon_type=amo.ADDON_PERSONA)
        eq_(len(leaders['leader_top']), 1)
        eq_(leaders['leader_top'][0]['user_id'], user2.id)

    def test_no_admins_or_staff_in_leaderboards(self):
        user2 = UserProfile.objects.get(email='admin@mozilla.com')
        self._give_points()
        self._give_points(status=amo.STATUS_LITE)
        self._give_points(user=user2, status=amo.STATUS_NOMINATED)
        leaders = ReviewerScore.get_leaderboards(self.user)
        eq_(leaders['user_rank'], 1)
        eq_(leaders['leader_near'], [])
        eq_(leaders['leader_top'][0]['user_id'], self.user.id)
        eq_(len(leaders['leader_top']), 1)  # Only the editor is here.
        assert user2.id not in [l['user_id'] for l in leaders['leader_top']], (
            'Unexpected admin user found in leaderboards.')

    def test_no_marketplace_points_in_amo_leaderboards(self):
        self._give_points()
        self._give_points(status=amo.STATUS_LITE)
        self._give_points(addon=self.app, status=amo.STATUS_NOMINATED)
        leaders = ReviewerScore.get_leaderboards(self.user,
                                                 types=amo.REVIEWED_AMO)
        eq_(leaders['leader_top'][0]['total'],
            amo.REVIEWED_SCORES[amo.REVIEWED_ADDON_FULL] +
            amo.REVIEWED_SCORES[amo.REVIEWED_ADDON_PRELIM])

    def test_no_amo_points_in_marketplace_leaderboards(self):
        self._give_points()
        self._give_points(status=amo.STATUS_LITE)
        self._give_points(addon=self.app, status=amo.STATUS_NOMINATED)
        leaders = ReviewerScore.get_leaderboards(
            self.user, types=amo.REVIEWED_MARKETPLACE)
        eq_(leaders['leader_top'][0]['total'],
            amo.REVIEWED_SCORES[amo.REVIEWED_WEBAPP_HOSTED])

    def test_get_breakdown(self):
        self._give_points()
        self._give_points(addon=amo.tests.app_factory())
        breakdown = ReviewerScore.get_breakdown(self.user)
        eq_(len(breakdown), 2)
        eq_(set([b.atype for b in breakdown]),
            set([amo.ADDON_EXTENSION, amo.ADDON_WEBAPP]))

    def test_get_breakdown_since(self):
        self._give_points()
        self._give_points(addon=amo.tests.app_factory())
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
        # Last user gets lower points by reviewing a persona.
        addon = self.addon
        addon.type = amo.ADDON_PERSONA
        self._give_points(user=last_user, addon=addon)
        leaders = ReviewerScore.get_leaderboards(last_user)
        eq_(leaders['user_rank'], 6)
        eq_(len(leaders['leader_top']), 3)
        eq_(len(leaders['leader_near']), 2)

    def test_all_users_by_score(self):
        user2 = UserProfile.objects.get(email='regular@mozilla.com')
        amo.REVIEWED_LEVELS[0]['points'] = 180
        self._give_points()
        self._give_points(status=amo.STATUS_LITE)
        self._give_points(user=user2, status=amo.STATUS_NOMINATED)
        users = ReviewerScore.all_users_by_score()
        eq_(len(users), 2)
        # First user.
        eq_(users[0]['total'], 180)
        eq_(users[0]['user_id'], self.user.id)
        eq_(users[0]['level'], amo.REVIEWED_LEVELS[0]['name'])
        # Second user.
        eq_(users[1]['total'], 120)
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
