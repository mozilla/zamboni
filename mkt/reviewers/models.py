import datetime

from django.core.cache import cache
from django.db import models
from django.db.models import Sum

import commonware.log

import mkt
import mkt.constants.comm as comm
from mkt.comm.utils import create_comm_note
from mkt.site.models import ManagerBase, ModelBase
from mkt.site.utils import cache_ns_key
from mkt.tags.models import Tag
from mkt.translations.fields import save_signal, TranslatedField
from mkt.users.models import UserProfile
from mkt.webapps.indexers import WebappIndexer
from mkt.webapps.models import Webapp
from mkt.websites.models import Website


user_log = commonware.log.getLogger('z.users')
QUEUE_TARAKO = 'tarako'


class CannedResponse(ModelBase):
    name = TranslatedField()
    response = TranslatedField(short=False)
    sort_group = models.CharField(max_length=255)

    class Meta:
        db_table = 'cannedresponses'

    def __unicode__(self):
        return unicode(self.name)


models.signals.pre_save.connect(save_signal, sender=CannedResponse,
                                dispatch_uid='cannedresponses_translations')


class ReviewerScore(ModelBase):
    user = models.ForeignKey(UserProfile, related_name='_reviewer_scores')
    addon = models.ForeignKey(Webapp, blank=True, null=True, related_name='+')
    website = models.ForeignKey(Website, blank=True, null=True,
                                related_name='+')
    score = models.SmallIntegerField()
    # For automated point rewards.
    note_key = models.SmallIntegerField(choices=mkt.REVIEWED_CHOICES.items(),
                                        default=0)
    # For manual point rewards with a note.
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = 'reviewer_scores'
        ordering = ('-created',)

    @classmethod
    def get_key(cls, key=None, invalidate=False):
        namespace = 'riscore'
        if not key:  # Assuming we're invalidating the namespace.
            cache_ns_key(namespace, invalidate)
            return
        else:
            # Using cache_ns_key so each cache val is invalidated together.
            ns_key = cache_ns_key(namespace, invalidate)
            return '%s:%s' % (ns_key, key)

    @classmethod
    def get_event(cls, addon, status, **kwargs):
        """Return the review event type constant.

        This is determined by the app type and the queue the addon is
        currently in (which is determined from the status).

        Note: We're not using addon.status because this is called after the
        status has been updated by the reviewer action.

        """
        if addon.is_packaged:
            if status in mkt.WEBAPPS_APPROVED_STATUSES:
                if addon.app_type_id == mkt.ADDON_WEBAPP_PRIVILEGED:
                    return mkt.REVIEWED_WEBAPP_PRIVILEGED_UPDATE
                else:
                    return mkt.REVIEWED_WEBAPP_UPDATE
            else:  # If it's not PUBLIC, assume it's a new submission.
                if addon.app_type_id == mkt.ADDON_WEBAPP_PRIVILEGED:
                    return mkt.REVIEWED_WEBAPP_PRIVILEGED
                else:
                    return mkt.REVIEWED_WEBAPP_PACKAGED
        else:  # It's a hosted app.
            in_rereview = kwargs.pop('in_rereview', False)
            if status in mkt.WEBAPPS_APPROVED_STATUSES and in_rereview:
                return mkt.REVIEWED_WEBAPP_REREVIEW
            else:
                return mkt.REVIEWED_WEBAPP_HOSTED

    @classmethod
    def get_extra_platform_points(cls, addon, status):
        """Gives extra points to reviews of apps that are compatible with
        multiple platforms, to reflect the extra effort involved.  Only new
        submissions get extra points (for now).

        """
        if status in mkt.WEBAPPS_APPROVED_STATUSES:
            return 0
        event = mkt.REVIEWED_WEBAPP_PLATFORM_EXTRA
        platform_bonus = mkt.REVIEWED_SCORES.get(event)
        devices_count = len(addon.device_types)
        if devices_count < 2:
            return 0
        else:
            return (devices_count - 1) * platform_bonus

    @classmethod
    def award_points(cls, user, addon, status, **kwargs):
        """Awards points to user based on an event and the queue.

        `event` is one of the `REVIEWED_` keys in constants.
        `status` is one of the `STATUS_` keys in constants.

        """
        event = cls.get_event(addon, status, **kwargs)
        score = mkt.REVIEWED_SCORES.get(event)
        if score:
            score += cls.get_extra_platform_points(addon, status)
            cls.objects.create(user=user, addon=addon, score=score,
                               note_key=event)
            cls.get_key(invalidate=True)
            user_log.info(
                (u'Awarding %s points to user %s for "%s" for addon %s'
                 % (score, user, mkt.REVIEWED_CHOICES[event], addon.id))
                .encode('utf-8'))
        return score

    @classmethod
    def award_moderation_points(cls, user, addon, review_id, undo=False):
        """Awards points to user based on moderated review."""
        event = (mkt.REVIEWED_APP_REVIEW if not undo else
                 mkt.REVIEWED_APP_REVIEW_UNDO)
        score = mkt.REVIEWED_SCORES.get(event)

        cls.objects.create(user=user, addon=addon, score=score, note_key=event)
        cls.get_key(invalidate=True)
        user_log.info(
            u'Awarding %s points to user %s for "%s" for review %s' % (
                score, user, mkt.REVIEWED_CHOICES[event], review_id))

    @classmethod
    def award_additional_review_points(cls, user, addon, queue):
        """Awards points to user based on additional (Tarako) review."""
        # TODO: generalize with other additional reviews queues
        event = mkt.REVIEWED_WEBAPP_TARAKO
        score = mkt.REVIEWED_SCORES.get(event)

        cls.objects.create(user=user, addon=addon, score=score, note_key=event)
        cls.get_key(invalidate=True)
        user_log.info(
            u'Awarding %s points to user %s for "%s" for addon %s' %
            (score, user, mkt.REVIEWED_CHOICES[event], addon.id))

    @classmethod
    def award_mark_abuse_points(cls, user, addon=None, website=None):
        """Awards points to user based on reading abuse reports."""
        if addon:
            event = mkt.REVIEWED_APP_ABUSE_REPORT
        elif website:
            event = mkt.REVIEWED_WEBSITE_ABUSE_REPORT
        else:
            # Nothing to do here.
            return
        score = mkt.REVIEWED_SCORES.get(event)

        cls.objects.create(user=user, addon=addon, website=website,
                           score=score, note_key=event)
        cls.get_key(invalidate=True)
        user_log.info(
            u'Awarding %s points to user %s for "%s"' %
            (score, user, mkt.REVIEWED_CHOICES[event]))

    @classmethod
    def get_total(cls, user):
        """Returns total points by user."""
        key = cls.get_key('get_total:%s' % user.id)
        val = cache.get(key)
        if val is not None:
            return val

        val = (ReviewerScore.objects.filter(user=user)
                                    .aggregate(total=Sum('score'))
                                    .values())[0]
        if val is None:
            val = 0

        cache.set(key, val, None)
        return val

    @classmethod
    def get_recent(cls, user, limit=5):
        """Returns most recent ReviewerScore records."""
        key = cls.get_key('get_recent:%s' % user.id)
        val = cache.get(key)
        if val is not None:
            return val

        val = ReviewerScore.objects.filter(user=user)

        val = list(val[:limit])
        cache.set(key, val, None)
        return val

    @classmethod
    def get_performance(cls, user):
        """Returns sum of reviewer points."""
        key = cls.get_key('get_performance:%s' % user.id)
        val = cache.get(key)
        if val is not None:
            return val

        sql = """
             SELECT `reviewer_scores`.*,
                    SUM(`reviewer_scores`.`score`) AS `total`
             FROM `reviewer_scores`
             LEFT JOIN `addons` ON (`reviewer_scores`.`addon_id`=`addons`.`id`)
             WHERE `reviewer_scores`.`user_id` = %s
             ORDER BY `total` DESC
        """
        val = list(ReviewerScore.objects.raw(sql, [user.id]))
        cache.set(key, val, None)
        return val

    @classmethod
    def get_performance_since(cls, user, since):
        """
        Returns sum of reviewer points since the given datetime.
        """
        key = cls.get_key('get_performance:%s:%s' % (
            user.id, since.isoformat()))
        val = cache.get(key)
        if val is not None:
            return val

        sql = """
             SELECT `reviewer_scores`.*,
                    SUM(`reviewer_scores`.`score`) AS `total`
             FROM `reviewer_scores`
             LEFT JOIN `addons` ON (`reviewer_scores`.`addon_id`=`addons`.`id`)
             WHERE `reviewer_scores`.`user_id` = %s AND
                   `reviewer_scores`.`created` >= %s
             ORDER BY `total` DESC
        """
        val = list(ReviewerScore.objects.raw(sql, [user.id, since]))
        cache.set(key, val, 3600)
        return val

    @classmethod
    def _leaderboard_query(cls, since=None, types=None):
        """
        Returns common SQL to leaderboard calls.
        """
        query = (cls.objects
                    .values_list('user__id', 'user__display_name')
                    .annotate(total=Sum('score'))
                    .exclude(user__groups__name__in=('No Reviewer Incentives',
                                                     'Staff', 'Admins'))
                    .order_by('-total'))

        if since is not None:
            query = query.filter(created__gte=since)

        if types is not None:
            query = query.filter(note_key__in=types)

        return query

    @classmethod
    def get_leaderboards(cls, user, days=7, types=None):
        """Returns leaderboards with ranking for the past given days.

        This will return a dict of 3 items::

            {'leader_top': [...],
             'leader_near: [...],
             'user_rank': (int)}

        If the user is not in the leaderboard, or if the user is in the top 5,
        'leader_near' will be an empty list and 'leader_top' will contain 5
        elements instead of the normal 3.

        """
        key = cls.get_key('get_leaderboards:%s' % user.id)
        val = cache.get(key)
        if val is not None:
            return val

        week_ago = datetime.date.today() - datetime.timedelta(days=days)

        leader_top = []
        leader_near = []

        query = cls._leaderboard_query(since=week_ago, types=types)
        scores = []

        user_rank = 0
        in_leaderboard = False
        for rank, row in enumerate(query, 1):
            user_id, name, total = row
            scores.append({
                'user_id': user_id,
                'name': name,
                'rank': rank,
                'total': int(total),
            })
            if user_id == user.id:
                user_rank = rank
                in_leaderboard = True

        if not in_leaderboard:
            leader_top = scores[:5]
        else:
            if user_rank <= 5:  # User is in top 5, show top 5.
                leader_top = scores[:5]
            else:
                leader_top = scores[:3]
                leader_near = [scores[user_rank - 2], scores[user_rank - 1]]
                try:
                    leader_near.append(scores[user_rank])
                except IndexError:
                    pass  # User is last on the leaderboard.

        val = {
            'leader_top': leader_top,
            'leader_near': leader_near,
            'user_rank': user_rank,
        }
        cache.set(key, val, None)
        return val

    @classmethod
    def all_users_by_score(cls):
        """
        Returns reviewers ordered by highest total points first.
        """
        query = cls._leaderboard_query()
        scores = []

        for row in query:
            user_id, name, total = row
            user_level = len(mkt.REVIEWED_LEVELS) - 1
            for i, level in enumerate(mkt.REVIEWED_LEVELS):
                if total < level['points']:
                    user_level = i - 1
                    break

            # Only show level if it changes.
            if user_level < 0:
                level = ''
            else:
                level = mkt.REVIEWED_LEVELS[user_level]['name']

            scores.append({
                'user_id': user_id,
                'name': name,
                'total': int(total),
                'level': level,
            })

        prev = None
        for score in reversed(scores):
            if score['level'] == prev:
                score['level'] = ''
            else:
                prev = score['level']

        return scores


ReviewerScore._meta.get_field('created').db_index = True


class EscalationQueue(ModelBase):
    addon = models.ForeignKey(Webapp)

    class Meta:
        db_table = 'escalation_queue'


class RereviewQueue(ModelBase):
    addon = models.ForeignKey(Webapp)

    class Meta:
        db_table = 'rereview_queue'

    @classmethod
    def flag(cls, addon, event, message=None):
        cls.objects.get_or_create(addon=addon)
        version = addon.current_version or addon.latest_version
        if message:
            mkt.log(event, addon, version, details={'comments': message})
        else:
            mkt.log(event, addon, version)

        # TODO: if we ever get rid of ActivityLog for reviewer notes, replace
        # all flag calls to use the comm constant and not have to use
        # ACTION_MAP.
        create_comm_note(addon, version, None, message,
                         note_type=comm.ACTION_MAP(event))


RereviewQueue._meta.get_field('created').db_index = True


def tarako_passed(review):
    """Add the tarako tag to the app."""
    tag = Tag(tag_text='tarako')
    tag.save_tag(review.app)
    WebappIndexer.index_ids([review.app.pk])


def tarako_failed(review):
    """Remove the tarako tag from the app."""
    tag = Tag(tag_text='tarako')
    tag.remove_tag(review.app)
    WebappIndexer.index_ids([review.app.pk])


class AdditionalReviewManager(ManagerBase):
    def unreviewed(self, queue, and_approved=False, descending=False):
        query = {
            'passed': None,
            'queue': queue,
        }
        if and_approved:
            query['app__status__in'] = mkt.WEBAPPS_APPROVED_STATUSES
        if descending:
            created_order = '-created'
        else:
            created_order = 'created'
        return (self.get_queryset()
                    .filter(**query)
                    .order_by('-app__priority_review', created_order))

    def latest_for_queue(self, queue):
        try:
            return self.get_queryset().filter(queue=queue).latest()
        except AdditionalReview.DoesNotExist:
            return None


class AdditionalReview(ModelBase):
    app = models.ForeignKey(Webapp)
    queue = models.CharField(max_length=30)
    passed = models.NullBooleanField()
    review_completed = models.DateTimeField(null=True)
    comment = models.CharField(null=True, blank=True, max_length=255)
    reviewer = models.ForeignKey('users.UserProfile', null=True, blank=True)

    objects = AdditionalReviewManager()

    class Meta:
        db_table = 'additional_review'
        unique_together = ('app', 'created')
        get_latest_by = 'created'

    @property
    def pending(self):
        return self.passed is None

    @property
    def failed(self):
        return self.passed is False

    def __init__(self, *args, **kwargs):
        super(AdditionalReview, self).__init__(*args, **kwargs)
        from mkt.reviewers.utils import log_reviewer_action
        self.log_reviewer_action = log_reviewer_action

    def execute_post_review_task(self):
        """
        Call the correct post-review function for the queue.
        """
        # TODO: Pull this function from somewhere based on self.queue.
        if self.passed is None:
            raise ValueError('cannot execute post-review task when unreviewed')
        elif self.passed:
            tarako_passed(self)
            action = mkt.LOG.PASS_ADDITIONAL_REVIEW
        else:
            tarako_failed(self)
            action = mkt.LOG.FAIL_ADDITIONAL_REVIEW
        self.log_reviewer_action(
            self.app, self.reviewer, self.comment or '', action,
            queue=self.queue)
        ReviewerScore.award_additional_review_points(self.reviewer, self.app,
                                                     self.queue)


def cleanup_queues(sender, instance, **kwargs):
    RereviewQueue.objects.filter(addon=instance).delete()
    EscalationQueue.objects.filter(addon=instance).delete()


models.signals.post_delete.connect(cleanup_queues, sender=Webapp,
                                   dispatch_uid='queue-addon-cleanup')


def update_search_index(sender, instance, **kwargs):
    WebappIndexer.index_ids([instance.addon_id])


for model in (RereviewQueue, EscalationQueue):
    models.signals.post_save.connect(
        update_search_index, sender=model,
        dispatch_uid='%s-save-update-index' % model._meta.model_name)
    models.signals.post_delete.connect(
        update_search_index, sender=model,
        dispatch_uid='%s-delete-update-index' % model._meta.model_name)
