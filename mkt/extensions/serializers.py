from rest_framework.serializers import ModelSerializer

from mkt.api.fields import TranslationSerializerField
from mkt.extensions.models import Extension


class ExtensionSerializer(ModelSerializer):
    name = TranslationSerializerField()

    class Meta:
        model = Extension
        fields = ['id', 'version', 'name', 'slug', 'status']
