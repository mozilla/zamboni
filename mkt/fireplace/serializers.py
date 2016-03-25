from rest_framework import serializers

from mkt.webapps.serializers import SimpleAppSerializer, SimpleESAppSerializer
from mkt.websites.serializers import ESWebsiteSerializer, WebsiteSerializer


class BaseFireplaceAppSerializer(object):
    def get_icons(self, app):
        # Fireplace only requires 64px and 128px icons.
        return {
            64: app.get_icon_url(64),
            128: app.get_icon_url(128)
        }


class FireplaceAppSerializer(BaseFireplaceAppSerializer, SimpleAppSerializer):

    class Meta(SimpleAppSerializer.Meta):
        fields = ['author', 'categories', 'content_ratings', 'current_version',
                  'description', 'device_types', 'feature_compatibility',
                  'file_size', 'homepage', 'icons', 'id',
                  'is_offline', 'is_packaged', 'last_updated', 'manifest_url',
                  'name', 'payment_required', 'premium_type', 'previews',
                  'price', 'price_locale', 'privacy_policy', 'promo_imgs',
                  'public_stats', 'release_notes', 'ratings', 'slug', 'status',
                  'support_email', 'support_url', 'tags', 'upsell', 'user']
        exclude = []


class FireplaceESAppSerializer(BaseFireplaceAppSerializer,
                               SimpleESAppSerializer):

    class Meta(SimpleESAppSerializer.Meta):
        fields = FireplaceAppSerializer.Meta.fields
        exclude = FireplaceAppSerializer.Meta.exclude

    def get_user_info(self, app):
        # Fireplace search should always be anonymous for extra-cacheability.
        return None


class FeedFireplaceESAppSerializer(BaseFireplaceAppSerializer,
                                   SimpleESAppSerializer):
    """
    Serializer for Fireplace Feed pages (mostly detail pages). Needs
    collection groups.
    """
    class Meta(SimpleESAppSerializer.Meta):
        fields = sorted(FireplaceAppSerializer.Meta.fields + ['group'])
        exclude = FireplaceAppSerializer.Meta.exclude
