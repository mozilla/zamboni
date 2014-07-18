from rest_framework.serializers import SerializerMethodField

from mkt.collections.serializers import (CollectionSerializer,
                                         CollectionMembershipField)
from mkt.webapps.serializers import SimpleAppSerializer, SimpleESAppSerializer


class BaseFireplaceAppSerializer(object):
    def get_icons(self, app):
        # Fireplace only requires 64px-sized icons.
        return {64: app.get_icon_url(64)}


class FireplaceAppSerializer(BaseFireplaceAppSerializer, SimpleAppSerializer):

    class Meta(SimpleAppSerializer.Meta):
        fields = ['author', 'banner_message', 'banner_regions', 'categories',
                  'content_ratings', 'current_version', 'description',
                  'device_types', 'homepage', 'icons', 'id', 'is_offline',
                  'is_packaged', 'manifest_url', 'name', 'payment_required',
                  'premium_type', 'previews', 'price', 'price_locale',
                  'privacy_policy', 'public_stats', 'release_notes', 'ratings',
                  'slug', 'status', 'support_email', 'support_url', 'upsell',
                  'user']
        exclude = []


class FireplaceESAppSerializer(BaseFireplaceAppSerializer,
                               SimpleESAppSerializer):
    weight = SerializerMethodField('get_weight')

    class Meta(SimpleESAppSerializer.Meta):
        fields = sorted(FireplaceAppSerializer.Meta.fields + ['weight'])
        exclude = FireplaceAppSerializer.Meta.exclude

    def get_weight(self, obj):
        return obj.es_data.get('weight', 1)

    def get_user_info(self, app):
        # Fireplace search should always be anonymous for extra-cacheability.
        return None


class FireplaceCollectionMembershipField(CollectionMembershipField):
    app_serializer_classes = {
        'es': FireplaceESAppSerializer,
        'normal': FireplaceAppSerializer,
    }


class FireplaceCollectionSerializer(CollectionSerializer):
    apps = FireplaceCollectionMembershipField(many=True, source='apps')
