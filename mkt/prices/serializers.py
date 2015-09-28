from rest_framework import serializers

from mkt.constants.payments import PROVIDER_LOOKUP_INVERTED
from mkt.prices.models import Price, price_locale


class PriceSerializer(serializers.ModelSerializer):
    prices = serializers.SerializerMethodField()
    localized = serializers.SerializerMethodField('get_localized_prices')
    pricePoint = serializers.CharField(source='name')
    name = serializers.CharField(source='tier_name')

    class Meta:
        model = Price

    def get_prices(self, obj):
        provider = self.context['request'].GET.get('provider', None)
        if provider:
            provider = PROVIDER_LOOKUP_INVERTED[provider]
        return obj.prices(provider=provider)

    def get_localized_prices(self, obj):
        region = self.context['request'].REGION

        for price in self.get_prices(obj):
            if price['region'] == region.id:
                result = price.copy()
                result.update({
                    'locale': price_locale(price['price'], price['currency']),
                    'region': region.name,
                })
                return result
        return {}
