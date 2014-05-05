from django.conf.urls import patterns, url

from . import views

urlpatterns = patterns(
    '',
    url('^elastic$', views.elastic, name='zadmin.elastic'),
    url('^manifest-revalidation$', views.manifest_revalidation,
        name='zadmin.manifest_revalidation'),
)
