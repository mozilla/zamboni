import datetime

from django.core.cache import cache
from django.db import models
from django.db.models import Sum

import commonware.log

import amo
import amo.models
from amo.utils import cache_ns_key
from mkt.access.models import Group
from mkt.developers.models import ActivityLog
from mkt.translations.fields import save_signal, TranslatedField
from mkt.users.models import UserProfile
from mkt.webapps.models import Addon


user_log = commonware.log.getLogger('z.users')


class CannedResponse(amo.models.ModelBase):
    name = TranslatedField()
    response = TranslatedField(short=False)
    sort_group = models.CharField(max_length=255)

    class Meta:
        db_table = 'cannedresponses'

    def __unicode__(self):
        return unicode(self.name)


models.signals.pre_save.connect(save_signal, sender=CannedResponse,
                                dispatch_uid='cannedresponses_translations')


class EditorSubscription(amo.models.ModelBase):
    user = models.ForeignKey(UserProfile)
    addon = models.ForeignKey(Addon)

    class Meta:
        db_table = 'editor_subscriptions'


class ReviewerScore(amo.models.ModelBase):
    user = models.ForeignKey(UserProfile, related_name='_reviewer_scores')
    addon = models.ForeignKey(Addon, blank=True, null=True, related_name='+')
    score = models.SmallIntegerField()
    # For automated point rewards.
    note_key = models.SmallIntegerField(choices=amo.REVIEWED_CHOICES.items(),
                                        default=0)
    # For manual point rewards with a note.
    note = models.CharField(max_length=255)

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

        This is determined by the addon.type and the queue the addon is
        currently in (which is determined from the status).

        Note: We're not using addon.status because this is called after the
        status has been updated by the reviewer action.

        """
        if addon.is_packaged:
            if status == amo.STATUS_PUBLIC:
                return amo.REVIEWED_WEBAPP_UPDATE
            else:  # If it's not PUBLIC, assume it's a new submission.
                return amo.REVIEWED_WEBAPP_PACKAGED
        else:  # It's a hosted app.
            in_rereview = kwargs.pop('in_rereview', False)
            if status == amo.STATUS_PUBLIC and in_rereview:
                return amo.REVIEWED_WEBAPP_REREVIEW
            else:
                return amo.REVIEWED_WEBAPP_HOSTED

    @classmethod
    def award_points(cls, user, addon, status, **kwargs):
        """Awards points to user based on an event and the queue.

        `event` is one of the `REVIEWED_` keys in constants.
        `status` is one of the `STATUS_` keys in constants.

        """
        event = cls.get_event(addon, status, **kwargs)
        score = amo.REVIEWED_SCORES.get(event)
        if score:
            cls.objects.create(user=user, addon=addon, score=score,
                               note_key=event)
            cls.get_key(invalidate=True)
            user_log.info(
                (u'Awarding %s points to user %s for "%s" for addon %s'
                 % (score, user, amo.REVIEWED_CHOICES[event], addon.id))
                .encode('utf-8'))
        return score

    @classmethod
    def award_moderation_points(cls, user, addon, review_id):
        """Awards points to user based on moderated review."""
        event = amo.REVIEWED_APP_REVIEW
        score = amo.REVIEWED_SCORES.get(event)

        cls.objects.create(user=user, addon=addon, score=score, note_key=event)
        cls.get_key(invalidate=True)
        user_log.info(
            u'Awarding %s points to user %s for "%s" for review %s' % (
                score, user, amo.REVIEWED_CHOICES[event], review_id))

    @classmethod
    def get_total(cls, user):
        """Returns total points by user."""
        key = cls.get_key('get_total:%s' % user.id)
        val = cache.get(key)
        if val is not None:
            return val

        val = (ReviewerScore.objects.no_cache().filter(user=user)
                                    .aggregate(total=Sum('score'))
                                    .values())[0]
        if val is None:
            val = 0

        cache.set(key, val, None)
        return val

    @classmethod
    def get_recent(cls, user, limit=5, addon_type=None):
        """Returns most recent ReviewerScore records."""
        key = cls.get_key('get_recent:%s' % user.id)
        val = cache.get(key)
        if val is not None:
            return val

        val = ReviewerScore.objects.no_cache().filter(user=user)
        if addon_type is not None:
            val.filter(addon__type=addon_type)

        val = list(val[:limit])
        cache.set(key, val, None)
        return val

    @classmethod
    def get_breakdown(cls, user):
        """Returns points broken down by addon type."""
        # TODO: This makes less sense now that we only have apps.
        key = cls.get_key('get_breakdown:%s' % user.id)
        val = cache.get(key)
        if val is not None:
            return val

        sql = """
             SELECT `reviewer_scores`.*,
                    SUM(`reviewer_scores`.`score`) AS `total`,
                    `addons`.`addontype_id` AS `atype`
             FROM `reviewer_scores`
             LEFT JOIN `addons` ON (`reviewer_scores`.`addon_id`=`addons`.`id`)
             WHERE `reviewer_scores`.`user_id` = %s
             GROUP BY `addons`.`addontype_id`
             ORDER BY `total` DESC
        """
        with amo.models.skip_cache():
            val = list(ReviewerScore.objects.raw(sql, [user.id]))
        cache.set(key, val, None)
        return val

    @classmethod
    def get_breakdown_since(cls, user, since):
        """
        Returns points broken down by addon type since the given datetime.
        """
        key = cls.get_key('get_breakdown:%s:%s' % (user.id, since.isoformat()))
        val = cache.get(key)
        if val is not None:
            return val

        sql = """
             SELECT `reviewer_scores`.*,
                    SUM(`reviewer_scores`.`score`) AS `total`,
                    `addons`.`addontype_id` AS `atype`
             FROM `reviewer_scores`
             LEFT JOIN `addons` ON (`reviewer_scores`.`addon_id`=`addons`.`id`)
             WHERE `reviewer_scores`.`user_id` = %s AND
                   `reviewer_scores`.`created` >= %s
             GROUP BY `addons`.`addontype_id`
             ORDER BY `total` DESC
        """
        with amo.models.skip_cache():
            val = list(ReviewerScore.objects.raw(sql, [user.id, since]))
        cache.set(key, val, 3600)
        return val

    @classmethod
    def _leaderboard_query(cls, since=None, types=None, addon_type=None):
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

        if addon_type is not None:
            query = query.filter(addon__type=addon_type)

        return query

    @classmethod
    def get_leaderboards(cls, user, days=7, types=None, addon_type=None):
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

        query = cls._leaderboard_query(since=week_ago, types=types,
                                       addon_type=addon_type)
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
            user_level = len(amo.REVIEWED_LEVELS) - 1
            for i, level in enumerate(amo.REVIEWED_LEVELS):
                if total < level['points']:
                    user_level = i - 1
                    break

            # Only show level if it changes.
            if user_level < 0:
                level = ''
            else:
                level = amo.REVIEWED_LEVELS[user_level]['name']

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


class EscalationQueue(amo.models.ModelBase):
    addon = models.ForeignKey(Addon)

    class Meta:
        db_table = 'escalation_queue'


class RereviewQueue(amo.models.ModelBase):
    addon = models.ForeignKey(Addon)

    class Meta:
        db_table = 'rereview_queue'

    @classmethod
    def flag(cls, addon, event, message=None):
        cls.objects.get_or_create(addon=addon)
        if message:
            amo.log(event, addon, addon.current_version,
                    details={'comments': message})
        else:
            amo.log(event, addon, addon.current_version)


def cleanup_queues(sender, instance, **kwargs):
    RereviewQueue.objects.filter(addon=instance).delete()
    EscalationQueue.objects.filter(addon=instance).delete()


models.signals.post_delete.connect(cleanup_queues, sender=Addon,
                                   dispatch_uid='queue-addon-cleanup')
