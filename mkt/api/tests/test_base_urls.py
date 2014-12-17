"""Some URLs for test_base.py"""

from django.conf.urls import patterns, url

from rest_framework.decorators import (authentication_classes,
                                       permission_classes)
from rest_framework.response import Response

from mkt.api.base import cors_api_view


@cors_api_view(['POST'], headers=('x-barfoo', 'x-foobar'))
@authentication_classes([])
@permission_classes([])
def _test_cors_api_view(request):
    return Response()


urlpatterns = patterns(
    '',
    url(r'^test-cors-api-view/', _test_cors_api_view,
        name='test-cors-api-view'),
)
