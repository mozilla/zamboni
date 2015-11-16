from rest_framework import serializers
from mkt.webapps.serializers import SimpleAppSerializer, SimpleESAppSerializer
from mkt.websites.serializers import ESWebsiteSerializer, WebsiteSerializer


class TVAppSerializer(SimpleAppSerializer):
    tv_featured = serializers.SerializerMethodField('get_tv_featured')

    class Meta(SimpleAppSerializer.Meta):
        fields = ['author', 'categories',
                  'content_ratings', 'current_version', 'description',
                  'file_size', 'homepage', 'hosted_url', 'icons', 'id',
                  'last_updated', 'manifest_url', 'name', 'previews',
                  'privacy_policy', 'promo_imgs', 'public_stats',
                  'release_notes', 'ratings', 'slug', 'status',
                  'support_email', 'support_url', 'tags',
                  'tv_featured', 'user']
        exclude = []

    def get_tv_featured(self, obj):
        return obj.tags.filter(tag_text='featured-tv').exists()


class TVESAppSerializer(SimpleESAppSerializer):
    tv_featured = serializers.BooleanField()

    class Meta(SimpleESAppSerializer.Meta):
        fields = TVAppSerializer.Meta.fields
        exclude = TVAppSerializer.Meta.exclude

    def get_user_info(self, app):
        # TV search should always be anonymous for extra-cacheability.
        return None

    def fake_object(self, data):
        o = SimpleESAppSerializer.fake_object(self, data)
        o.tv_featured = data['tv_featured']
        return o


class TVWebsiteSerializer(WebsiteSerializer):
    tv_featured = serializers.SerializerMethodField('get_tv_featured')

    class Meta(WebsiteSerializer.Meta):
        fields = ['categories', 'description', 'icons', 'id',
                  'keywords', 'name', 'promo_imgs', 'short_name',
                  'tv_featured', 'tv_url', 'url']

    def get_tv_featured(self, obj):
        return obj.keywords.filter(tag_text='featured-tv').exists()


class TVESWebsiteSerializer(ESWebsiteSerializer):
    tv_featured = serializers.BooleanField()

    class Meta(ESWebsiteSerializer.Meta):
        fields = TVWebsiteSerializer.Meta.fields

    def fake_object(self, data):
        o = ESWebsiteSerializer.fake_object(self, data)
        o.tv_featured = data['tv_featured']
        return o
