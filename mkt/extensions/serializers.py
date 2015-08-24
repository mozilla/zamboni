from rest_framework.serializers import ModelSerializer

from mkt.api.fields import ReverseChoiceField, TranslationSerializerField
from mkt.constants.base import STATUS_CHOICES_API_v2
from mkt.extensions.models import Extension


class ExtensionSerializer(ModelSerializer):
    name = TranslationSerializerField()
    status = ReverseChoiceField(choices_dict=STATUS_CHOICES_API_v2)

    class Meta:
        model = Extension
        fields = ['id', 'version', 'name', 'slug', 'status']
