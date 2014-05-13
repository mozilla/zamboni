from django.conf.urls import patterns, url

from . import views


urlpatterns = patterns('',
    url('^tags/top$', views.top_cloud, name='tags.top_cloud'),
)
