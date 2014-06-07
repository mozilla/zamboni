from django.conf.urls import include, patterns, url

from rest_framework.routers import SimpleRouter

from mkt.api.base import SubRouterWithFormat
from mkt.api.v1.urls import urlpatterns as v1_urls
from mkt.api.views import endpoint_removed
from mkt.feed.views import (FeedAppImageViewSet, FeedAppViewSet,
                            FeedBrandViewSet, FeedBuilderView,
                            FeedCollectionImageViewSet, FeedCollectionViewSet,
                            FeedElementSearchView, FeedItemViewSet)


feed = SimpleRouter()
feed.register(r'apps', FeedAppViewSet, base_name='feedapps')
feed.register(r'brands', FeedBrandViewSet, base_name='feedbrands')
feed.register(r'collections', FeedCollectionViewSet,
              base_name='feedcollections')
feed.register(r'items', FeedItemViewSet, base_name='feeditems')

subfeedapp = SubRouterWithFormat()
subfeedapp.register('image', FeedAppImageViewSet,
                    base_name='feed-app-image')

subfeedcollection = SubRouterWithFormat()
subfeedcollection.register('image', FeedCollectionImageViewSet,
                    base_name='feed-collection-image')

urlpatterns = patterns('',
    url(r'^rocketfuel/collections/.*', endpoint_removed),
    url(r'^feed/builder/$', FeedBuilderView.as_view(),
        name='feed.builder'),
    url(r'^feed/element/search/$', FeedElementSearchView.as_view(),
        name='feed.element-search'),
    url(r'^feed/', include(feed.urls)),
    url(r'^feed/apps/', include(subfeedapp.urls)),
    url(r'^feed/collections/', include(subfeedcollection.urls)),
) + v1_urls
