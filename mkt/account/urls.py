from django.conf.urls import include, patterns, url

from mkt.account.views import (AccountView, FeedbackView, FxALoginView,
                               GroupsViewSet, InstalledViewSet, LoginView,
                               LogoutView, NewsletterView, PermissionsView,
                               TOSView)
from mkt.feed.views import FeedShelfViewSet
from mkt.users import views

drf_patterns = patterns(
    '',
    url('^feedback/$', FeedbackView.as_view(), name='account-feedback'),
    url('^installed/mine/$',
        InstalledViewSet.as_view({'get': 'list'}), name='installed-apps'),
    url('^installed/mine/remove_app/$',
        InstalledViewSet.as_view({'post': 'remove_app'}),
        name='installed-apps-remove'),
    # Native FxA login view.
    url('^login/$', LoginView.as_view(), name='account-login'),
    # Oauth FxA login view.
    url('^fxa-login/$', FxALoginView.as_view(), name='fxa-account-login'),
    url('^logout/$', LogoutView.as_view(), name='account-logout'),
    url('^newsletter/$', NewsletterView.as_view(), name='account-newsletter'),
    url('^permissions/(?P<pk>[^/]+)/$', PermissionsView.as_view(),
        name='account-permissions'),
    url('^settings/(?P<pk>[^/]+)/$', AccountView.as_view(),
        name='account-settings'),
    url(r'^shelves/$', FeedShelfViewSet.as_view(
        {'get': 'mine'}), name='feedshelves-mine'),
    url('^groups/(?P<pk>[^/]+)/$',
        GroupsViewSet.as_view({'get': 'list', 'post': 'create',
                               'delete': 'destroy'}),
        name='account-groups'),
    url('^devtos/$', TOSView.as_view(), name='account-devtos'),
)

api_patterns = patterns(
    '',
    url('^account/', include(drf_patterns)),
)

user_patterns = patterns(
    '',
    url('^ajax$', views.ajax, name='users.ajax'),
)
