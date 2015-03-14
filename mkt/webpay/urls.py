from django.conf.urls import include, patterns, url

from rest_framework import routers

from mkt.prices.views import PricesViewSet
from mkt.webpay.views import (FailureNotificationView,
                              PreparePayWebAppView, PreparePayInAppView,
                              ProductIconViewSet, sig_check, StatusPayView)


api = routers.SimpleRouter()
api.register(r'prices', PricesViewSet)
api.register(r'product/icon', ProductIconViewSet)

urlpatterns = patterns(
    '',
    url(r'^', include(api.urls)),
    url(r'^webpay/', include(api.urls)),
    url(r'^webpay/status/(?P<uuid>[^/]+)/', StatusPayView.as_view(),
        name='webpay-status'),
    url(r'^webpay/prepare/', PreparePayWebAppView.as_view(),
        name='webpay-prepare'),
    url(r'^webpay/inapp/prepare/', PreparePayInAppView.as_view(),
        name='webpay-prepare-inapp'),
    url(r'^webpay/failure/(?P<pk>[^/]+)/',
        FailureNotificationView.as_view(),
        name='webpay-failurenotification'),
    url(r'^webpay/sig_check/$', sig_check, name='webpay-sig_check')
)
