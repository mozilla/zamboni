from rest_framework import serializers

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
