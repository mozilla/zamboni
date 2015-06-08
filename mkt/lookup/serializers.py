from rest_framework import serializers

from django.core.urlresolvers import reverse

import mkt
from mkt.webapps.serializers import ESAppSerializer
from mkt.websites.serializers import ESWebsiteSerializer


class AppLookupSerializer(ESAppSerializer):
    url = serializers.SerializerMethodField('get_app_summary_url')
    status = serializers.SerializerMethodField('get_app_status')

    class Meta(ESAppSerializer.Meta):
        fields = ['app_slug', 'id', 'name', 'status', 'url']

    def get_app_summary_url(self, obj):
        return reverse('lookup.app_summary', args=[obj.id])

    def get_app_status(self, obj):
        """
        Return slug of app status.

        In Elasticsearch we store both `status` and `is_disabled`, but
        `Webapp.is_disabled` returns True if either `STATUS_DISABLED` or
        `disabled_by_user` is True, so this pulls it back apart.

        """
        if obj.status != mkt.STATUS_DISABLED and obj._is_disabled:
            status = 'disabled'
        else:
            status = mkt.STATUS_CHOICES_API_v2[obj.status]
        return status


class WebsiteLookupSerializer(ESWebsiteSerializer):
    url = serializers.SerializerMethodField('get_website_summary_url')

    class Meta(ESWebsiteSerializer.Meta):
        fields = ['id', 'name', 'url']

    def get_website_summary_url(self, obj):
        return reverse('lookup.website_summary', args=[obj.id])
