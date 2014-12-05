from django.conf.urls import include, patterns, url

from mkt.account.views import (fxa_preverify_view, fxa_preverify_key,
                               AccountView, AccountInfoView,
                               ConfirmFxAVerificationView, FeedbackView,
                               FxALoginView, InstalledViewSet, LoginView,
                               LogoutView, NewsletterView, PermissionsView)
from mkt.feed.views import FeedShelfViewSet
from mkt.users import views

drf_patterns = patterns('',
    url('^feedback/$', FeedbackView.as_view(), name='account-feedback'),
    url('^installed/mine/$',
        InstalledViewSet.as_view({'get': 'list'}), name='installed-apps'),
    url('^installed/mine/remove_app/$',
        InstalledViewSet.as_view({'post': 'remove_app'}),
        name='installed-apps-remove'),
    url('^login/$', LoginView.as_view(), name='account-login'),
    url('^fxa-login/$', FxALoginView.as_view(), name='fxa-account-login'),
    url('^fxa-preverify/$', fxa_preverify_view, name='fxa-preverify'),
    url('^fxa-preverify/confirm/(?P<email>[^/]+)$',
        ConfirmFxAVerificationView.as_view(),
        name='fxa-confirm-preverify'),
    url('^fxa-preverify-key/$', fxa_preverify_key, name='fxa-preverify-key'),
    url('^logout/$', LogoutView.as_view(), name='account-logout'),
    url('^newsletter/$', NewsletterView.as_view(), name='account-newsletter'),
    url('^permissions/(?P<pk>[^/]+)/$', PermissionsView.as_view(),
        name='account-permissions'),
    url('^settings/(?P<pk>[^/]+)/$', AccountView.as_view(),
        name='account-settings'),
    url('^info/(?P<email>[^/]+)$', AccountInfoView.as_view(),
        name='account-info'),
    url(r'^shelves/$', FeedShelfViewSet.as_view(
        {'get': 'mine'}), name='feedshelves-mine'),
)

api_patterns = patterns('',
    url('^account/', include(drf_patterns)),
)

user_patterns = patterns('',
    url('^ajax$', views.ajax, name='users.ajax'),
    url('^browserid-login', views.browserid_login,
        name='users.browserid_login'),
)
