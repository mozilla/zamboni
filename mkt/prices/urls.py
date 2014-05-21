from django.conf.urls import include, patterns, url

from rest_framework import routers
from mkt.prices.views import PricesViewSet

api = routers.SimpleRouter()
api.register(r'prices', PricesViewSet)

urlpatterns = patterns(
    '',
    url(r'^', include(api.urls)),
)
