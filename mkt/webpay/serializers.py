from rest_framework import serializers

from mkt.webpay.models import ProductIcon

class ProductIconSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField('get_url')

    def get_url(self, obj):
        if not obj.pk:
            return ''
        return obj.url()

    class Meta:
        model = ProductIcon
        exclude = ('format',)
