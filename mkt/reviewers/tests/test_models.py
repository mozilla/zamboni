# -*- coding: utf8 -*-
import time
from datetime import datetime

from django.conf import settings
from django.core import mail

import mock
from nose.tools import eq_, ok_

import amo
import amo.tests

from mkt.constants import comm
from mkt.comm.models import CommunicationNote
from mkt.reviewers.models import (
    AdditionalReview, QUEUE_TARAKO, RereviewQueue, ReviewerScore,
    send_tarako_mail, tarako_failed, tarako_passed)
from mkt.site.fixtures import fixture
from mkt.tags.models import Tag
from mkt.users.models import UserProfile
from mkt.webapps.models import AddonDeviceType, Webapp


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

    def check_event(self, status, event, **kwargs):
        eq_(ReviewerScore.get_event(self.app, status, **kwargs), event, (
            'Score event status:%s was not %s' % (status, event)))

    def test_events_webapps(self):
        self.app = amo.tests.app_factory()
        self.check_event(amo.STATUS_PENDING,
                         amo.REVIEWED_WEBAPP_HOSTED)

        RereviewQueue.objects.create(addon=self.app)
        self.check_event(amo.STATUS_PUBLIC,
                         amo.REVIEWED_WEBAPP_REREVIEW, in_rereview=True)
        self.check_event(amo.STATUS_UNLISTED,
                         amo.REVIEWED_WEBAPP_REREVIEW, in_rereview=True)
        self.check_event(amo.STATUS_APPROVED,
                         amo.REVIEWED_WEBAPP_REREVIEW, in_rereview=True)
        RereviewQueue.objects.all().delete()

        self.app.is_packaged = True
        self.check_event(amo.STATUS_PENDING,
                         amo.REVIEWED_WEBAPP_PACKAGED)
        self.check_event(amo.STATUS_PUBLIC,
                         amo.REVIEWED_WEBAPP_UPDATE)
        self.check_event(amo.STATUS_UNLISTED,
                         amo.REVIEWED_WEBAPP_UPDATE)
        self.check_event(amo.STATUS_APPROVED,
                         amo.REVIEWED_WEBAPP_UPDATE)

        self.app.latest_version.is_privileged = True
        self.check_event(amo.STATUS_PENDING,
                         amo.REVIEWED_WEBAPP_PRIVILEGED)
        self.check_event(amo.STATUS_PUBLIC,
                         amo.REVIEWED_WEBAPP_PRIVILEGED_UPDATE)
        self.check_event(amo.STATUS_UNLISTED,
                         amo.REVIEWED_WEBAPP_PRIVILEGED_UPDATE)
        self.check_event(amo.STATUS_APPROVED,
                         amo.REVIEWED_WEBAPP_PRIVILEGED_UPDATE)

    def test_award_points(self):
        self._give_points()
        eq_(ReviewerScore.objects.all()[0].score,
            amo.REVIEWED_SCORES[amo.REVIEWED_WEBAPP_HOSTED])

    def test_award_moderation_points(self):
        ReviewerScore.award_moderation_points(self.user, self.app, 1)
        score = ReviewerScore.objects.all()[0]
        eq_(score.score, amo.REVIEWED_SCORES.get(amo.REVIEWED_APP_REVIEW))
        eq_(score.note_key, amo.REVIEWED_APP_REVIEW)

    def test_award_additional_review_points(self):
        ReviewerScore.award_additional_review_points(self.user, self.app,
                                                     QUEUE_TARAKO)
        score = ReviewerScore.objects.all()[0]
        eq_(score.score, amo.REVIEWED_SCORES.get(amo.REVIEWED_WEBAPP_TARAKO))
        eq_(score.note_key, amo.REVIEWED_WEBAPP_TARAKO)

    def test_extra_platform_points(self):
        AddonDeviceType.objects.create(addon=self.app, device_type=1)
        self._give_points()
        score1 = amo.REVIEWED_SCORES[amo.REVIEWED_WEBAPP_HOSTED]
        eq_(ReviewerScore.objects.order_by('-pk').first().score, score1)

        AddonDeviceType.objects.create(addon=self.app, device_type=2)
        self._give_points()
        score2 = (amo.REVIEWED_SCORES[amo.REVIEWED_WEBAPP_HOSTED] +
                  amo.REVIEWED_SCORES[amo.REVIEWED_WEBAPP_PLATFORM_EXTRA])
        eq_(ReviewerScore.objects.order_by('-pk').first().score, score2)

        AddonDeviceType.objects.create(addon=self.app, device_type=3)
        self._give_points()
        score3 = (amo.REVIEWED_SCORES[amo.REVIEWED_WEBAPP_HOSTED] +
                  amo.REVIEWED_SCORES[amo.REVIEWED_WEBAPP_PLATFORM_EXTRA] * 2)
        eq_(ReviewerScore.objects.order_by('-pk').first().score, score3)

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


class TestAdditionalReview(amo.tests.TestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        self.app = Webapp.objects.get(pk=337141)
        self.review = AdditionalReview.objects.create(
            app=self.app, queue=QUEUE_TARAKO)
        self.tarako_passed = self.patch('mkt.reviewers.models.tarako_passed')
        self.tarako_failed = self.patch('mkt.reviewers.models.tarako_failed')
        self.log_reviewer_action = self.patch_object(
            self.review, 'log_reviewer_action')
        self.award_additional_review_points = self.patch(
            'mkt.reviewers.models.ReviewerScore.award_additional_review_points')

    def patch(self, patch_string):
        patcher = mock.patch(patch_string)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked

    def patch_object(self, obj, attr):
        patcher = mock.patch.object(obj, attr)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked

    def test_execute_post_review_task_calls_tarako_passed_when_passed(self):
        self.review.passed = True
        ok_(not self.tarako_passed.called,
            'expected tarako_passed to be not called')
        self.review.execute_post_review_task()
        self.tarako_passed.assert_called_with(self.review)
        ok_(not self.tarako_failed.called,
            'expected tarako_failed to be not called')

    def test_execute_post_review_task_calls_tarako_failed_when_failed(self):
        self.review.passed = False
        ok_(not self.tarako_failed.called,
            'expected tarako_failed to be not called')
        self.review.execute_post_review_task()
        self.tarako_failed.assert_called_with(self.review)
        ok_(not self.tarako_passed.called,
            'expected tarako_passed to be not called')

    def test_execute_post_review_task_raises_an_error_when_unreviewed(self):
        self.review.passed = None
        ok_(not self.tarako_passed.called,
            'expected tarako_passed to be not called')
        ok_(not self.tarako_failed.called,
            'expected tarako_failed to be not called')
        with self.assertRaises(ValueError):
            self.review.execute_post_review_task()
        ok_(not self.tarako_passed.called,
            'expected tarako_passed to be not called')
        ok_(not self.tarako_failed.called,
            'expected tarako_failed to be not called')

    def test_log_reviewer_action_when_failed(self):
        reviewer = UserProfile()
        comment = 'It would not start'
        self.review.passed = False
        self.review.comment = comment
        self.review.reviewer = reviewer
        ok_(not self.log_reviewer_action.called)
        self.review.execute_post_review_task()
        self.log_reviewer_action.assert_called_with(
            self.app, reviewer, comment, amo.LOG.FAIL_ADDITIONAL_REVIEW,
            queue=QUEUE_TARAKO)

    def test_log_reviewer_action_when_passed(self):
        reviewer = UserProfile()
        comment = 'It is totally awesome'
        self.review.passed = True
        self.review.comment = comment
        self.review.reviewer = reviewer
        ok_(not self.log_reviewer_action.called)
        self.review.execute_post_review_task()
        self.log_reviewer_action.assert_called_with(
            self.app, reviewer, comment, amo.LOG.PASS_ADDITIONAL_REVIEW,
            queue=QUEUE_TARAKO)

    def test_log_reviewer_action_blank_comment_when_none(self):
        reviewer = UserProfile()
        self.review.passed = True
        self.review.comment = None
        self.review.reviewer = reviewer
        ok_(not self.log_reviewer_action.called)
        self.review.execute_post_review_task()
        self.log_reviewer_action.assert_called_with(
            self.app, reviewer, '', amo.LOG.PASS_ADDITIONAL_REVIEW,
            queue=QUEUE_TARAKO)

    def test_get_points(self):
        reviewer = UserProfile()
        self.review.passed = True
        self.review.reviewer = reviewer
        ok_(not self.award_additional_review_points.called)
        self.review.execute_post_review_task()
        self.award_additional_review_points.assert_called_with(
            reviewer, self.app, QUEUE_TARAKO)


class TestAdditionalReviewManager(amo.tests.TestCase):

    def setUp(self):
        self.unreviewed = AdditionalReview.objects.create(
            app=Webapp.objects.create(), queue='queue-one')
        self.unreviewed_too = AdditionalReview.objects.create(
            app=Webapp.objects.create(), queue='queue-one')
        self.passed = AdditionalReview.objects.create(
            app=Webapp.objects.create(), queue='queue-one', passed=True)
        self.other_queue = AdditionalReview.objects.create(
            app=Webapp.objects.create(), queue='queue-two')

    def test_unreviewed_none_approved_allow_unapproved(self):
        eq_(set([self.unreviewed, self.unreviewed_too]),
            set(AdditionalReview.objects.unreviewed(queue='queue-one')))

    def test_unreviewed_none_approved_only_approved(self):
        eq_([], list(AdditionalReview.objects.unreviewed(
            queue='queue-one', and_approved=True)))

    def test_unreviewed_and_approved_all_approved(self):
        self.unreviewed.app.update(status=amo.STATUS_PUBLIC)
        self.unreviewed_too.app.update(status=amo.STATUS_APPROVED)
        eq_(set([self.unreviewed, self.unreviewed_too]),
            set(AdditionalReview.objects.unreviewed(queue='queue-one')))

    def test_unreviewed_and_approved_one_approved_allow_unapproved(self):
        self.unreviewed.app.update(status=amo.STATUS_PUBLIC)
        self.unreviewed_too.app.update(status=amo.STATUS_REJECTED)
        eq_(set([self.unreviewed, self.unreviewed_too]),
            set(AdditionalReview.objects.unreviewed(queue='queue-one')))

    def test_unreviewed_and_approved_one_approved_only_approved(self):
        self.unreviewed.app.update(status=amo.STATUS_PUBLIC)
        self.unreviewed_too.app.update(status=amo.STATUS_REJECTED)
        eq_(set([self.unreviewed]),
            set(AdditionalReview.objects.unreviewed(
                queue='queue-one', and_approved=True)))

    def test_becoming_approved_lists_the_app_when_showing_approved(self):
        self.unreviewed.app.update(status=amo.STATUS_PUBLIC)
        eq_(set([self.unreviewed]),
            set(AdditionalReview.objects.unreviewed(
                queue='queue-one', and_approved=True)))
        self.unreviewed_too.app.update(status=amo.STATUS_PUBLIC)
        # Caching might return the old queryset, but we don't want it to.
        eq_(set([self.unreviewed, self.unreviewed_too]),
            set(AdditionalReview.objects.unreviewed(
                queue='queue-one', and_approved=True)))

    def test_unreviewed_priority_order(self):
        priority = AdditionalReview.objects.create(
            app=Webapp.objects.create(priority_review=True),
            queue='queue-one')
        priority.update(created=datetime(2014, 10, 15))
        self.unreviewed.update(created=datetime(2014, 10, 14))
        self.unreviewed_too.update(created=datetime(2014, 10, 10))
        eq_([priority, self.unreviewed_too, self.unreviewed],
            list(AdditionalReview.objects.unreviewed(queue='queue-one')))

    def test_unreviewed_priority_order_descending(self):
        priority = AdditionalReview.objects.create(
            app=Webapp.objects.create(priority_review=True),
            queue='queue-one')
        priority.update(created=datetime(2014, 10, 15))
        self.unreviewed.update(created=datetime(2014, 10, 14))
        self.unreviewed_too.update(created=datetime(2014, 10, 10))
        eq_([priority, self.unreviewed, self.unreviewed_too],
            list(AdditionalReview.objects.unreviewed(
                queue='queue-one', descending=True)))


class BaseTarakoFunctionsTestCase(amo.tests.TestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        self.app = Webapp.objects.get(pk=337141)
        self.review = AdditionalReview.objects.create(
            app=self.app, queue=QUEUE_TARAKO)
        self.tag, _ = Tag.objects.get_or_create(tag_text='tarako')

    def patch(self, patch_string):
        patcher = mock.patch(patch_string)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked


class TestTarakoFunctions(BaseTarakoFunctionsTestCase):
    def setUp(self):
        super(TestTarakoFunctions, self).setUp()
        self.index = self.patch('mkt.reviewers.models.WebappIndexer.index_ids')
        self.send_tarako_mail = self.patch(
            'mkt.reviewers.models.send_tarako_mail')

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

    def test_tarako_passed_sends_tarako_mail(self):
        ok_(not self.send_tarako_mail.called)
        tarako_passed(self.review)
        self.send_tarako_mail.assert_called_with(self.review)

    def test_tarako_failed_removes_tarako_tag(self):
        self.tag.save_tag(self.app)
        ok_(self.tag_exists(), 'expected the tarako tag')
        tarako_failed(self.review)
        ok_(not self.tag_exists(), 'expected no tarako tag')

    def test_tarako_failed_reindexes_the_app(self):
        ok_(not self.index.called)
        tarako_failed(self.review)
        self.index.assert_called_with([self.app.pk])

    def test_tarako_failed_sends_tarako_mail(self):
        ok_(not self.send_tarako_mail.called)
        tarako_failed(self.review)
        self.send_tarako_mail.assert_called_with(self.review)


class TestSendTarakoMail(BaseTarakoFunctionsTestCase):
    def setUp(self):
        super(TestSendTarakoMail, self).setUp()
        self.send_mail = self.patch('mkt.reviewers.models.send_mail_jinja')
        self.award_additional_review_points = self.patch(
            'mkt.reviewers.models.ReviewerScore.award_additional_review_points')

    def test_send_tarako_mail_review_passed(self):
        ok_(not self.send_mail.called)
        self.review.passed = True
        send_tarako_mail(self.review)
        self.send_mail.assert_called_with(
            'Low-memory devices review passed',
            'reviewers/emails/tarako_review_complete.txt',
            {'review': self.review},
            recipient_list=['steamcube@mozilla.com'],
            from_email=settings.MKT_REVIEWERS_EMAIL)

    def test_send_tarako_mail_review_failed(self):
        ok_(not self.send_mail.called)
        self.review.passed = False
        send_tarako_mail(self.review)
        self.send_mail.assert_called_with(
            'Low-memory devices review failed',
            'reviewers/emails/tarako_review_complete.txt',
            {'review': self.review},
            recipient_list=[u'steamcube@mozilla.com'],
            from_email=settings.MKT_REVIEWERS_EMAIL)

    def test_send_tarako_mail_passed_comm_dashboard(self):
        self.create_switch('comm-dashboard')
        ok_(not self.send_mail.called)
        self.review.passed = True
        send_tarako_mail(self.review)
        ok_(not self.send_mail.called)

    def test_send_tarako_mail_failed_comm_dashboard(self):
        self.create_switch('comm-dashboard')
        ok_(not self.send_mail.called)
        self.review.passed = False
        send_tarako_mail(self.review)
        ok_(not self.send_mail.called)

    def test_comm_mail_pass(self):
        self.create_switch('comm-dashboard')
        self.review.passed = True
        self.review.execute_post_review_task()
        ok_(CommunicationNote.objects.filter(
            note_type=comm.ADDITIONAL_REVIEW_PASSED).exists())
        ok_('Additional review passed' in mail.outbox[0].subject)
        ok_('passed' in mail.outbox[0].body)

    def test_comm_mail_fail(self):
        self.create_switch('comm-dashboard')
        self.review.passed = False
        self.review.execute_post_review_task()
        ok_(CommunicationNote.objects.filter(
            note_type=comm.ADDITIONAL_REVIEW_FAILED).exists())
        ok_('Additional review failed' in mail.outbox[0].subject)
        ok_('not passed' in mail.outbox[0].body)


class TestRereviewQueue(amo.tests.TestCase):
    def setUp(self):
        self.app = amo.tests.app_factory()

    def test_flag_creates_notes(self):
        RereviewQueue.flag(self.app, amo.LOG.REREVIEW_PREMIUM_TYPE_UPGRADE)
        eq_(self.app.threads.all()[0].notes.all()[0].note_type,
            comm.REREVIEW_PREMIUM_TYPE_UPGRADE)
