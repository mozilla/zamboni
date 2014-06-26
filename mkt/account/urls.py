from django.conf.urls import include, patterns, url

from mkt.users import views

from mkt.account.views import (AccountView, FeedbackView, FxaLoginView,
                               InstalledView, LoginView, LogoutView,
                               NewsletterView, PermissionsView)


drf_patterns = patterns('',
    url('^feedback/$', FeedbackView.as_view(), name='account-feedback'),
    url('^installed/mine/$', InstalledView.as_view(), name='installed-apps'),
    url('^login/$', LoginView.as_view(), name='account-login'),
    url('^fxa-login/$', FxaLoginView.as_view(), name='fxa-account-login'),
    url('^logout/$', LogoutView.as_view(), name='account-logout'),
    url('^newsletter/$', NewsletterView.as_view(), name='account-newsletter'),
    url('^permissions/(?P<pk>[^/]+)/$', PermissionsView.as_view(),
        name='account-permissions'),
    url('^settings/(?P<pk>[^/]+)/$', AccountView.as_view(),
        name='account-settings'),
)

api_patterns = patterns('',
    url('^account/', include(drf_patterns)),
)

user_patterns = patterns('',
    url('^ajax$', views.ajax, name='users.ajax'),
    url('^browserid-login', views.browserid_login,
        name='users.browserid_login'),
)
