from django.conf.urls import patterns, url

from . import views


stats_api_patterns = patterns(
    '',
    url(r'^stats/global/totals/$', views.GlobalStatsTotal.as_view(),
        name='global_stats_total'),
    url(r'^stats/global/(?P<metric>[^/]+)/$', views.GlobalStats.as_view(),
        name='global_stats'),
    url(r'^stats/app/(?P<pk>[^/<>"\']+)/totals/$',
        views.AppStatsTotal.as_view(), name='app_stats_total'),
    url(r'^stats/app/(?P<pk>[^/<>"\']+)/(?P<metric>[^/]+)/$',
        views.AppStats.as_view(), name='app_stats'),
)


txn_api_patterns = patterns(
    '',
    url(r'^transaction/(?P<transaction_id>[^/]+)/$',
        views.TransactionAPI.as_view(),
        name='transaction_api'),
)
