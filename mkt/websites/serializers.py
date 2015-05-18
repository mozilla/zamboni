from drf_compound_fields.fields import ListField
from rest_framework import serializers

from mkt.api.fields import TranslationSerializerField
from mkt.search.serializers import BaseESSerializer
from mkt.websites.models import Website


class WebsiteSerializer(serializers.ModelSerializer):
    categories = ListField(serializers.CharField())
    description = TranslationSerializerField()
    device_types = ListField(serializers.CharField(), source='device_names')
    id = serializers.IntegerField(source='pk')
    short_name = TranslationSerializerField()
    name = TranslationSerializerField()
    title = TranslationSerializerField()

    # FIXME: keywords, regions, icons... try to stay compatible with Webapp API
    # as much as possible.

    class Meta:
        model = Website
        fields = ['categories', 'description', 'device_types', 'id',
                  'mobile_url', 'name', 'short_name', 'title', 'url']


class ESWebsiteSerializer(BaseESSerializer, WebsiteSerializer):
    def fake_object(self, data):
        """Create a fake instance of Website from ES data."""
        obj = Website(id=data['id'])

        # Set basic attributes on the fake instance using the data from ES.
        self._attach_fields(obj, data, ('default_locale', 'url'))

        # Set attributes with names that don't exactly match the one on the
        # model.
        obj.categories = data['category']
        obj.devices = data['device']

        # Attach translations for all translated attributes. obj.default_locale
        # should be set first for this to work.
        self._attach_translations(
            obj, data, ('description', 'name', 'short_name', 'title'))

        # Some methods might need the raw data from ES, put it on obj.
        obj.es_data = data

        return obj


class ReviewerESWebsiteSerializer(ESWebsiteSerializer):
    class Meta(ESWebsiteSerializer.Meta):
        model = Website
        fields = ESWebsiteSerializer.Meta.fields + ['status']
