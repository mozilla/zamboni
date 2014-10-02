from django.conf.urls import include, patterns, url

from rest_framework.routers import SimpleRouter

from mkt.fireplace.views import (AppViewSet, CollectionViewSet,
                                 ConsumerInfoView, SearchView)


apps = SimpleRouter()
apps.register(r'app', AppViewSet, base_name='fireplace-app')


collections = SimpleRouter()
collections.register(r'collection', CollectionViewSet,
                     base_name='fireplace-collection')


urlpatterns = patterns('',
    url(r'^fireplace/', include(apps.urls)),
    url(r'^fireplace/', include(collections.urls)),
    url(r'^fireplace/consumer-info/',
        ConsumerInfoView.as_view(),
        name='fireplace-consumer-info'),
    # /featured/ is not used by fireplace anymore, but still used by yogafire,
    # so we have to keep it, it's just an alias to the regular search instead
    # of including extra data about collections.
    url(r'^fireplace/search/featured/',
        SearchView.as_view(),
        name='fireplace-featured-search-api'),
    url(r'^fireplace/search/',
        SearchView.as_view(),
        name='fireplace-search-api'),
)
