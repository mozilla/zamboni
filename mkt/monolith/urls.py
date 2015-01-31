from django.conf.urls import patterns, url

from mkt.monolith.views import MonolithView


urlpatterns = patterns(
    '',
    url(r'^monolith/data/', MonolithView.as_view(), name='monolith-list'),
)
