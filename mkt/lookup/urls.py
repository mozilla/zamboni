from django.conf.urls import include, patterns, url

from . import views


# These views all start with user ID.
user_patterns = patterns(
    '',
    url(r'^$', views.user_summary,
        name='lookup.user_summary'),
    url(r'^purchases$', views.user_purchases,
        name='lookup.user_purchases'),
    url(r'^activity$', views.user_activity,
        name='lookup.user_activity'),
    url(r'^delete$', views.user_delete,
        name='lookup.user_delete'),
)


# These views all start with app/addon ID.
app_patterns = patterns(
    '',
    url(r'^$', views.app_summary,
        name='lookup.app_summary'),
    url(r'^activity$', views.app_activity,
        name='lookup.app_activity'),
)


# These views all start with website/<ID>.
website_patterns = patterns(
    '',
    url(r'^$', views.website_summary,
        name='lookup.website_summary'),
    url(r'^edit$', views.website_edit,
        name='lookup.website_edit'),
)


# These views all start with transaction ID.
transaction_patterns = patterns(
    '',
    url(r'^$', views.transaction_summary,
        name='lookup.transaction_summary'),
    url(r'^refund$', views.transaction_refund,
        name='lookup.transaction_refund'),
)


urlpatterns = patterns(
    '',
    url(r'^$', views.home, name='lookup.home'),
    url(r'^bango-portal/(?P<package_id>[^/]+)/$',
        views.bango_portal_from_package,
        name='lookup.bango_portal_from_package'),
    url(r'^app_search$', views.AppLookupSearchView.as_view(),
        name='lookup.app_search'),
    url(r'^transaction_search$', views.transaction_search,
        name='lookup.transaction_search'),
    url(r'^user_search$', views.user_search,
        name='lookup.user_search'),
    url(r'^website_search$', views.WebsiteLookupSearchView.as_view(),
        name='lookup.website_search'),
    url(r'^group_search$', views.group_search,
        name='lookup.group_search'),
    (r'^app/(?P<addon_id>[^/]+)/', include(app_patterns)),
    (r'^website/(?P<addon_id>[^/]+)/', include(website_patterns)),
    (r'^transaction/(?P<tx_uuid>[^/]+)/',
     include(transaction_patterns)),
    (r'^user/(?P<user_id>[^/]+)/', include(user_patterns)),
    url(r'^group/(?P<group_id>[^/]+)/$', views.group_summary,
        name='lookup.group_summary'),
)
