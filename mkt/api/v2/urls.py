from django.conf.urls import include, patterns, url

from rest_framework.routers import SimpleRouter

import mkt.feed.views as views
from mkt.api.base import SubRouterWithFormat
from mkt.api.v1.urls import urlpatterns as v1_urls
from mkt.api.views import endpoint_removed
from mkt.search.views import RocketbarViewV2


feed = SimpleRouter()
feed.register(r'apps', views.FeedAppViewSet, base_name='feedapps')
feed.register(r'brands', views.FeedBrandViewSet, base_name='feedbrands')
feed.register(r'collections', views.FeedCollectionViewSet,
              base_name='feedcollections')
feed.register(r'shelves', views.FeedShelfViewSet, base_name='feedshelves')
feed.register(r'items', views.FeedItemViewSet, base_name='feeditems')

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
    url(r'^apps/search/rocketbar/', RocketbarViewV2.as_view(),
        name='rocketbar-search-api'),
    url(r'^rocketfuel/collections/.*', endpoint_removed),
    url(r'^feed/builder/$', views.FeedBuilderView.as_view(),
        name='feed.builder'),
    url(r'^feed/elements/search/$', views.FeedElementSearchView.as_view(),
        name='feed.element-search'),
    url(r'^feed/get/', views.FeedView.as_view(), name='feed.get'),
    url(r'^feed/', include(feed.urls)),
    url(r'^feed/apps/', include(subfeedapp.urls)),
    url(r'^feed/collections/', include(subfeedcollection.urls)),
    url(r'^feed/shelves/', include(subfeedshelf.urls)),
    url(r'^feed/shelves/(?P<pk>[^/.]+)/publish/$',
        views.FeedShelfPublishView.as_view(),
        name='feed-shelf-publish'),
    url(r'^fireplace/feed/(?P<item_type>[\w]+)/(?P<slug>[^/.]+)/$',
        views.FeedElementGetView.as_view(), name='feed.feed_element_get'),
    url(r'^transonic/feed/(?P<item_type>[\w]+)/$',
        views.FeedElementListView.as_view(), name='feed.feed_element_list'),
) + v1_urls
