from django.conf.urls import include, patterns, url

from rest_framework.routers import SimpleRouter

import mkt
import mkt.feed.views as views
from mkt.api.base import SubRouterWithFormat
from mkt.api.v1.urls import urlpatterns as v1_urls
from mkt.api.views import endpoint_removed
from mkt.comm.views import CommAppListView, ThreadViewSetV2
from mkt.langpacks.views import LangPackViewSet
from mkt.operators.views import OperatorPermissionViewSet
from mkt.recommendations.views import RecommendationView
from mkt.search.views import (MultiSearchView, NonPublicSearchView,
                              NoRegionSearchView, RocketbarViewV2)
from mkt.websites.views import (WebsiteMetadataScraperView, WebsiteSearchView,
                                WebsiteView, WebsiteSubmissionView)


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
subfeedshelf.register('image_landing', views.FeedShelfLandingImageViewSet,
                      base_name='feed-shelf-landing-image')


langpacks = SimpleRouter()
langpacks.register(r'', LangPackViewSet, base_name='langpack')

comm_thread = SimpleRouter()
comm_thread.register(r'', ThreadViewSetV2, base_name='comm-thread')


urlpatterns = patterns(
    '',
    url(r'^apps/search/featured/.*', endpoint_removed),
    url(r'^rocketfuel/collections/.*', endpoint_removed),

    url(r'^account/operators/$', OperatorPermissionViewSet.as_view(
        {'get': 'list'}), name='operator-permissions'),

    url(r'^apps/recommend/$', RecommendationView.as_view(),
        name='apps-recommend'),
    url(r'^apps/search/rocketbar/$', RocketbarViewV2.as_view(),
        name='rocketbar-search-api'),
    url(r'^apps/search/non-public/$', NonPublicSearchView.as_view(),
        name='non-public-search-api'),
    url(r'^apps/search/no-region/$',
        NoRegionSearchView.as_view(),
        name='no-region-search-api'),

    url(r'^comm/app/%s' % mkt.APP_SLUG,
        CommAppListView.as_view({'get': 'list'}), name='comm-app-list'),
    url(r'^comm/thread', include(comm_thread.urls)),

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
    # Nix FP version once FP using consumer/feed with app_serializer=fireplace.
    url(r'^fireplace/feed/(?P<item_type>[\w]+)/(?P<slug>[^/.]+)/$',
        views.FeedElementGetView.as_view(), name='feed.fire_feed_element_get'),
    url(r'^consumer/feed/(?P<item_type>[\w]+)/(?P<slug>[^/.]+)/$',
        views.FeedElementGetView.as_view(), name='feed.feed_element_get'),
    url(r'^transonic/feed/(?P<item_type>[\w]+)/$',
        views.FeedElementListView.as_view(), name='feed.feed_element_list'),

    url(r'^langpacks', include(langpacks.urls)),
    url(r'^websites/search/', WebsiteSearchView.as_view(),
        name='website-search-api'),
    url(r'^websites/website/(?P<pk>[^/.]+)/', WebsiteView.as_view(),
        name='website-detail'),
    url(r'^websites/scrape/', WebsiteMetadataScraperView.as_view(),
        name='website-scrape'),
    url(r'^websites/submit/', WebsiteSubmissionView.as_view(),
        name='website-submit'),
    url(r'^multi-search/', MultiSearchView.as_view(),
        name='multi-search-api'),
) + v1_urls
