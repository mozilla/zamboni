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
