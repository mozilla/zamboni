from django.core.urlresolvers import reverse
from django.conf.urls import include, patterns, url
from django.shortcuts import redirect
from django.utils.encoding import iri_to_uri

from rest_framework.routers import SimpleRouter

from mkt.fireplace.views import (AppViewSet, ConsumerInfoView, MultiSearchView,
                                 SearchView)
from mkt.site.decorators import allow_cross_site_request


apps = SimpleRouter()
apps.register(r'app', AppViewSet, base_name='fireplace-app')


@allow_cross_site_request
def redirect_to_feed_element(request, slug):
    url = reverse('api-v2:feed.fire_feed_element_get',
                  kwargs={'item_type': 'collections', 'slug': slug})
    query_string = request.META.get('QUERY_STRING', '')
    if query_string:
        query_string = '?' + iri_to_uri(query_string)
    return redirect(url + query_string, permanent=True)


urlpatterns = patterns(
    '',
    url(r'^fireplace/', include(apps.urls)),

    # Compatibility for old apps that still hit the rocketfuel collection API,
    # we redirect them to the feed.
    url(r'^fireplace/collection/(?P<slug>[^/.]+)/$', redirect_to_feed_element,
        name='feed.fire_rocketfuel_compat'),

    url(r'^fireplace/consumer-info/$',
        ConsumerInfoView.as_view(),
        name='fireplace-consumer-info'),
    # /featured/ is not used by fireplace anymore, but still used by yogafire,
    # so we have to keep it, it's just an alias to the regular search instead
    # of including extra data about collections.
    url(r'^fireplace/search/featured/$',
        SearchView.as_view(),
        name='fireplace-featured-search-api'),
    url(r'^fireplace/search/$',
        SearchView.as_view(),
        name='fireplace-search-api'),
    url(r'^fireplace/multi-search/$',
        MultiSearchView.as_view(),
        name='fireplace-multi-search-api'),
)
