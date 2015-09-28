from rest_framework import serializers

from mkt.api.fields import TranslationSerializerField
from mkt.reviewers.models import (AdditionalReview, CannedResponse,
                                  QUEUE_TARAKO, ReviewerScore)
from mkt.webapps.models import Webapp
from mkt.webapps.serializers import ESAppSerializer


class ReviewingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Webapp
        fields = ('resource_uri', )

    resource_uri = serializers.HyperlinkedRelatedField(view_name='app-detail',
                                                       read_only=True,
                                                       source='*')


SEARCH_FIELDS = [u'device_types', u'id', u'is_escalated', u'is_packaged',
                 u'name', u'premium_type', u'price', u'slug', u'status']


class ReviewersESAppSerializer(ESAppSerializer):
    latest_version = serializers.SerializerMethodField()
    is_escalated = serializers.BooleanField()

    class Meta(ESAppSerializer.Meta):
        fields = SEARCH_FIELDS + ['latest_version', 'is_escalated']

    def get_latest_version(self, obj):
        v = obj.es_data.latest_version
        return {
            'has_editor_comment': v.has_editor_comment,
            'has_info_request': v.has_info_request,
            'is_privileged': v.is_privileged,
            'status': v.status,
        }


class AdditionalReviewSerializer(serializers.ModelSerializer):
    """Developer facing AdditionalReview serializer."""

    app = serializers.PrimaryKeyRelatedField(queryset=Webapp.objects)
    comment = serializers.CharField(max_length=255, read_only=True)

    class Meta:
        model = AdditionalReview
        fields = ['id', 'app', 'queue', 'passed', 'created', 'modified',
                  'review_completed', 'comment']
        # Everything is read-only.
        read_only_fields = ['id', 'passed', 'created', 'modified',
                            'review_completed', 'reviewer']

    def pending_review_exists(self, queue, app_id):
        return (AdditionalReview.objects.unreviewed(queue=queue)
                                        .filter(app_id=app_id)
                                        .exists())

    def validate_queue(self, queue):
        if queue != QUEUE_TARAKO:
            raise serializers.ValidationError('is not a valid choice')
        return queue

    def validate_app(self, app):
        queue = self.initial_data.get('queue')
        if queue and app and self.pending_review_exists(queue, app):
            raise serializers.ValidationError('has a pending review')
        return app


class ReviewerAdditionalReviewSerializer(AdditionalReviewSerializer):
    """Reviewer facing AdditionalReview serializer."""

    comment = serializers.CharField(max_length=255, required=False)
    passed = serializers.BooleanField(required=True)

    class Meta:
        model = AdditionalReview
        fields = AdditionalReviewSerializer.Meta.fields
        read_only_fields = list(
            set(AdditionalReviewSerializer.Meta.read_only_fields) -
            set(['passed', 'reviewer']))

    def validate(self, attrs):
        if self.instance and self.instance.passed is not None:
            raise serializers.ValidationError('has already been reviewed')
        elif attrs.get('passed') not in (True, False):
            raise serializers.ValidationError('passed must be a boolean value')
        else:
            return attrs


class CannedResponseSerializer(serializers.ModelSerializer):
    name = TranslationSerializerField(required=True)
    response = TranslationSerializerField(required=True)

    class Meta:
        model = CannedResponse


class ReviewerScoreSerializer(serializers.ModelSerializer):

    class Meta:
        model = ReviewerScore
        fields = ['id', 'note', 'user', 'score']

    def validate(self, attrs):
        if 'note' not in attrs and not self.partial:
            attrs['note'] = ''
        return attrs
