from django.conf.urls import include, patterns, url

from rest_framework.routers import SimpleRouter

from mkt.extensions.views import (ExtensionSearchView, ExtensionViewSet,
                                  ReviewersExtensionViewSet, ValidationViewSet)

extensions = SimpleRouter()
extensions.register(r'validation', ValidationViewSet,
                    base_name='extension-validation')
extensions.register(r'extension', ExtensionViewSet)
extensions.register(r'queue', ReviewersExtensionViewSet,
                    base_name='extension-queue')


urlpatterns = patterns(
    '',
    url(r'', include(extensions.urls)),
    url(r'search/$', ExtensionSearchView.as_view(), name='extension-search'),
)
