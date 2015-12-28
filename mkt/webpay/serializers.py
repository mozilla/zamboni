from rest_framework import serializers

from mkt.purchase.models import Contribution
from mkt.webpay.models import ProductIcon


class ProductIconSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    def get_url(self, obj):
        if not obj.pk:
            return ''
        return obj.url()

    class Meta:
        model = ProductIcon
        exclude = ('format',)


class ContributionSerializer(serializers.ModelSerializer):
    """
    Dummy Contribution serializer.

    This doesn't expose anything because the views that use it
    do not return any data. However, DRF will raise an AssertionError
    if a view does not declare a serializer.
    """

    class Meta:
        model = Contribution
