from rest_framework import serializers

from mkt.api.forms import SchemeURLValidator as URLValidator
from mkt.inapp.models import InAppProduct


class InAppProductSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    app = serializers.SlugRelatedField(read_only=True, slug_field='app_slug',
                                       source='webapp')
    price_id = serializers.PrimaryKeyRelatedField(source='price')
    name = serializers.CharField()
    logo_url = serializers.CharField(
            validators=[URLValidator(schemes=['http', 'https'])],
            required=False)

    class Meta:
        model = InAppProduct
        fields = ['id', 'app', 'price_id', 'name', 'logo_url']
