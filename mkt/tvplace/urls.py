from django.conf.urls import include, patterns, url

from rest_framework.routers import SimpleRouter

from mkt.tvplace.views import AppViewSet, MultiSearchView, SearchView

apps = SimpleRouter()
apps.register(r'app', AppViewSet, base_name='tv-app')

urlpatterns = patterns(
    '',
    url(r'^tv/', include(apps.urls)),
    url(r'^tv/search/$',
        SearchView.as_view(),
        name='tv-search-api'),
    url(r'^tv/multi-search/$',
        MultiSearchView.as_view(),
        name='tv-multi-search-api'),

)
