import django_filters
from rest_framework.mixins import RetrieveModelMixin, ListModelMixin
from rest_framework.permissions import AllowAny
from rest_framework.viewsets import GenericViewSet

from mkt.api.base import CORSMixin, MarketplaceView
from mkt.prices.models import Price
from mkt.prices.serializers import PriceSerializer
from mkt.api.authentication import RestAnonymousAuthentication


class PriceFilter(django_filters.FilterSet):
    pricePoint = django_filters.CharFilter(name="name")

    class Meta:
        model = Price
        fields = ['pricePoint']


class PricesViewSet(MarketplaceView, CORSMixin, ListModelMixin,
                    RetrieveModelMixin, GenericViewSet):
    queryset = Price.objects.filter(active=True).order_by('price')
    serializer_class = PriceSerializer
    cors_allowed_methods = ['get']
    authentication_classes = [RestAnonymousAuthentication]
    permission_classes = [AllowAny]
    filter_class = PriceFilter
