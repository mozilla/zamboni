from django.conf.urls import include, patterns, url

from rest_framework.routers import SimpleRouter

import mkt.feed.views as views
from mkt.api.base import SubRouterWithFormat
from mkt.api.v1.urls import urlpatterns as v1_urls
from mkt.api.views import endpoint_removed


feed = SimpleRouter()
feed.register(r'apps', views.FeedAppViewSet, base_name='feedapps')
feed.register(r'brands', views.FeedBrandViewSet, base_name='feedbrands')
feed.register(r'collections', views.FeedCollectionViewSet,
              base_name='feedcollections')
feed.register(r'items', views.FeedItemViewSet, base_name='feeditems')
feed.register(r'shelves', views.FeedShelfViewSet, base_name='feedshelves')

subfeedapp = SubRouterWithFormat()
subfeedapp.register('image', views.FeedAppImageViewSet,
                    base_name='feed-app-image')

subfeedcollection = SubRouterWithFormat()
subfeedcollection.register('image', views.FeedCollectionImageViewSet,
                    base_name='feed-collection-image')

subfeedshelf = SubRouterWithFormat()
subfeedshelf.register('image', views.FeedShelfImageViewSet,
                      base_name='feed-shelf-image')

urlpatterns = patterns('',
    url(r'^rocketfuel/collections/.*', endpoint_removed),
    url(r'^feed/builder/$', views.FeedBuilderView.as_view(),
        name='feed.builder'),
    url(r'^feed/elements/search/$', views.FeedElementSearchView.as_view(),
        name='feed.element-search'),
    url(r'^feed/', include(feed.urls)),
    url(r'^feed/apps/', include(subfeedapp.urls)),
    url(r'^feed/collections/', include(subfeedcollection.urls)),
    url(r'^feed/shelves/', include(subfeedshelf.urls)),
    url(r'^feed/shelves/(?P<pk>[^/.]+)/publish',
        views.FeedShelfPublishView.as_view(),
        name='feed-shelf-publish'),
) + v1_urls
