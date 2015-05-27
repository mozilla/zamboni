from rest_framework import serializers

from django.core.urlresolvers import reverse

from mkt.webapps.serializers import ESAppSerializer


class AppLookupSerializer(ESAppSerializer):
    url = serializers.SerializerMethodField('get_app_summary_url')

    class Meta(ESAppSerializer.Meta):
        fields = ['id', 'url', 'app_slug', 'name']

    def get_app_summary_url(self, obj):
        return reverse('lookup.app_summary', args=[obj.id])


class WebsiteLookupSerializer(ESAppSerializer):
    url = serializers.SerializerMethodField('get_website_summary_url')

    class Meta(ESAppSerializer.Meta):
        fields = ['id', 'url', 'name']

    def get_app_summary_url(self, obj):
        return reverse('lookup.website_summary', args=[obj.id])
