from django.conf.urls import include, patterns, url

from rest_framework.routers import SimpleRouter

from mkt.extensions.views import (ExtensionSearchView, ExtensionViewSet,
                                  ValidationViewSet)

extensions = SimpleRouter()
extensions.register(r'validation', ValidationViewSet,
                    base_name='extension-validation')
extensions.register(r'extension', ExtensionViewSet)


urlpatterns = patterns(
    '',
    url(r'', include(extensions.urls)),
    url(r'search', ExtensionSearchView.as_view(), name='extension-search'),
)
