from django.conf import settings
from django.conf.urls import include, patterns, url

import mkt
from . import views


def fireplace_route(path, name=None):
    """
    Helper function for building Fireplace URLs. `path` is the URL route,
    and `name` (if specified) is the name given to the route.
    """
    kwargs = {}
    if name:
        kwargs['name'] = name
    return url('^%s$' % path, views.commonplace, {'repo': 'fireplace'},
               **kwargs)

fireplace_reviews_patterns = patterns(
    '',
    fireplace_route('flag', 'ratings.flag'),
    fireplace_route('delete', 'ratings.delete'),
)

fireplace_app_patterns = patterns(
    '',
    fireplace_route('', 'detail'),
    fireplace_route('abuse', 'detail.abuse'),
    fireplace_route('privacy', 'detail.privacy'),
    fireplace_route('recommended', 'recommended'),
    fireplace_route('reviews/', 'ratings.list'),
    fireplace_route('reviews/add', 'ratings.add'),
    url('^(?P<review_id>\d+)/', include(fireplace_reviews_patterns)),
)

fireplace_website_patterns = patterns(
    '',
    fireplace_route('', 'website.detail'),
)

urlpatterns = patterns(
    '',
    # Fireplace:
    url('^$', views.commonplace, {'repo': 'fireplace'}, name='home'),
    url('^server.html$', views.commonplace, {'repo': 'fireplace'},
        name='commonplace.fireplace'),
    url('^fxa-authorize$', views.fxa_authorize,
        name='commonplace.fxa_authorize'),
    (r'^app/%s/' % mkt.APP_SLUG, include(fireplace_app_patterns)),
    (r'^website/(?P<pk>\d+)', include(fireplace_website_patterns)),
    url(r'^iframe-install.html/?$', views.iframe_install,
        name='commonplace.iframe-install'),
    url(r'^potatolytics.html$', views.potatolytics,
        name='commonplace.potatolytics'),

    # Commbadge:
    url('^comm/app/%s$' % mkt.APP_SLUG, views.commonplace,
        {'repo': 'commbadge'},
        name='commonplace.commbadge.app_dashboard'),
    url('^comm/thread/(?P<thread_id>\d+)$', views.commonplace,
        {'repo': 'commbadge'},
        name='commonplace.commbadge.show_thread'),
    url('^comm/.*$', views.commonplace, {'repo': 'commbadge'},
        name='commonplace.commbadge'),

    # Transonic:
    url('^curate/.*$', views.commonplace, {'repo': 'transonic'},
        name='commonplace.transonic'),

    # Stats:
    url('^statistics/app/%s$' % mkt.APP_SLUG, views.commonplace,
        {'repo': 'marketplace-stats'},
        name='commonplace.stats.app_dashboard'),
    url('^statistics/.*$', views.commonplace, {'repo': 'marketplace-stats'},
        name='commonplace.stats'),

    # Operator Dashboard:
    url('^operators/.*$', views.commonplace,
        {'repo': 'marketplace-operator-dashboard'},
        name='commonplace.operatordashboard'),

    # Content Tools:
    url('^content/addon/review/%s$' % mkt.APP_SLUG, views.commonplace,
        {'repo': 'marketplace-content-tools'},
        name='commonplace.content.addon_review'),
    url('^content/addon/dashboard/%s$' % mkt.APP_SLUG, views.commonplace,
        {'repo': 'marketplace-content-tools'},
        name='commonplace.content.addon_manage'),
    url('^content/.*$', views.commonplace,
        {'repo': 'marketplace-content-tools'},
        name='commonplace.content'),
)

if settings.DEBUG:
    # More Fireplace stuff, only for local dev:
    urlpatterns += patterns(
        '',
        fireplace_route('category/.*'),
        fireplace_route('categories'),
        fireplace_route('collection/.*'),
        fireplace_route('debug'),
        fireplace_route('feed/.*'),
        fireplace_route('feedback'),
        fireplace_route('fxa-authorize'),
        fireplace_route('new'),
        fireplace_route('popular'),
        fireplace_route('privacy-policy'),
        fireplace_route('purchases'),
        fireplace_route('search/?'),
        fireplace_route('settings'),
        fireplace_route('terms-of-use'),
        fireplace_route('tests'),
    )
