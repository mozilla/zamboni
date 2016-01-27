from rest_framework import serializers
from mkt.webapps.serializers import SimpleAppSerializer, SimpleESAppSerializer
from mkt.websites.serializers import ESWebsiteSerializer, WebsiteSerializer


class TVAppSerializer(SimpleAppSerializer):
    tv_featured = serializers.IntegerField()

    class Meta(SimpleAppSerializer.Meta):
        fields = ['author', 'categories',
                  'content_ratings', 'current_version', 'description',
                  'file_size', 'homepage', 'hosted_url', 'icons', 'id',
                  'last_updated', 'manifest_url', 'name', 'privacy_policy',
                  'promo_imgs', 'public_stats', 'release_notes',
                  'ratings', 'slug', 'status', 'support_email', 'support_url',
                  'tags', 'tv_featured', 'user']
        exclude = []


class TVESAppSerializer(SimpleESAppSerializer):
    tv_featured = serializers.IntegerField()

    class Meta(SimpleESAppSerializer.Meta):
        fields = TVAppSerializer.Meta.fields
        exclude = TVAppSerializer.Meta.exclude

    def get_user_info(self, app):
        # TV search should always be anonymous for extra-cacheability.
        return None


class TVWebsiteSerializer(WebsiteSerializer):
    tv_featured = serializers.IntegerField()

    class Meta(WebsiteSerializer.Meta):
        fields = ['categories', 'description', 'developer_name', 'icons', 'id',
                  'keywords', 'name', 'promo_imgs', 'short_name',
                  'tv_featured', 'tv_url', 'url']


class TVESWebsiteSerializer(ESWebsiteSerializer):
    tv_featured = serializers.IntegerField()

    class Meta(ESWebsiteSerializer.Meta):
        fields = TVWebsiteSerializer.Meta.fields
