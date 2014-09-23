from rest_framework import serializers

from mkt.api.fields import TranslationSerializerField
from mkt.reviewers.models import AdditionalReview, CannedResponse, QUEUE_TARAKO
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
    latest_version = serializers.SerializerMethodField('get_latest_version')
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

    app = serializers.PrimaryKeyRelatedField()
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

    def validate_queue(self, attrs, source):
        if attrs[source] != QUEUE_TARAKO:
            raise serializers.ValidationError('is not a valid choice')
        return attrs

    def validate_app(self, attrs, source):
        queue = attrs.get('queue')
        app = attrs.get('app')
        if queue and app and self.pending_review_exists(queue, app):
            raise serializers.ValidationError('has a pending review')
        return attrs


class ReviewerAdditionalReviewSerializer(AdditionalReviewSerializer):
    """Reviewer facing AdditionalReview serializer."""

    comment = serializers.CharField(max_length=255, required=False)

    class Meta:
        model = AdditionalReview
        fields = AdditionalReviewSerializer.Meta.fields
        read_only_fields = list(
            set(AdditionalReviewSerializer.Meta.read_only_fields) -
            set(['passed', 'reviewer']))

    def validate(self, attrs):
        if self.object.passed is not None:
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
