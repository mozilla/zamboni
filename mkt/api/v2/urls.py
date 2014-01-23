from django.conf.urls import include, patterns, url

from rest_framework.routers import SimpleRouter

from mkt.api.base import SubRouterWithFormat
from mkt.api.v1.urls import urlpatterns as v1_urls
from mkt.api.views import endpoint_removed
from mkt.collections.views import CollectionImageViewSet, CollectionViewSet
from mkt.feed.views import FeedAppViewSet, FeedItemViewSet


feed = SimpleRouter()
feed.register(r'apps', FeedAppViewSet, base_name='feedapps')
feed.register(r'collections', CollectionViewSet, base_name='collections')
feed.register(r'items', FeedItemViewSet, base_name='feeditems')

subcollections = SubRouterWithFormat()
subcollections.register('image', CollectionImageViewSet,
                        base_name='collection-image')

urlpatterns = patterns('',
    url(r'^rocketfuel/collections/.*', endpoint_removed),
    url(r'^feed/', include(feed.urls)),
    url(r'^feed/collections/', include(subcollections.urls)),
) + v1_urls
