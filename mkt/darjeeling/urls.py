from django.conf.urls import patterns, url

from mkt.darjeeling.views import DarjeelingAppList


urlpatterns = patterns('',
    url(r'^darjeeling/list/',
        DarjeelingAppList.as_view(),
        name='darjeeling-list'),
)
