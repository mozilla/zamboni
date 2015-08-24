from rest_framework.serializers import ModelSerializer

from mkt.api.fields import ReverseChoiceField, TranslationSerializerField
from mkt.constants.base import STATUS_CHOICES_API_v2
from mkt.extensions.models import Extension
from mkt.search.serializers import BaseESSerializer


class ExtensionSerializer(ModelSerializer):
    name = TranslationSerializerField()
    status = ReverseChoiceField(choices_dict=STATUS_CHOICES_API_v2)

    class Meta:
        model = Extension
        fields = ['id', 'version', 'name', 'slug', 'status']


class ESExtensionSerializer(BaseESSerializer, ExtensionSerializer):
    def fake_object(self, data):
        """Create a fake instance of Extension from ES data."""
        obj = Extension(id=data['id'])

        # Set basic attributes we'll need on the fake instance using the data
        # from ES.
        self._attach_fields(
            obj, data, ('default_language', 'slug', 'status', 'version'))

        # Attach translations for all translated attributes.
        # obj.default_language should be set first for this to work.
        self._attach_translations(
            obj, data, ('name', ))

        # Some methods might need the raw data from ES, put it on obj.
        obj.es_data = data

        return obj
