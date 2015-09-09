from django.conf.urls import include, patterns, url

from rest_framework.routers import SimpleRouter
from rest_framework_nested.routers import NestedSimpleRouter

from mkt.extensions.views import (ExtensionSearchView, ExtensionVersionViewSet,
                                  ExtensionViewSet, ReviewersExtensionViewSet,
                                  ValidationViewSet)

extensions = SimpleRouter()
extensions.register(r'validation', ValidationViewSet,
                    base_name='extension-validation')
extensions.register(r'extension', ExtensionViewSet)
extensions.register(r'queue', ReviewersExtensionViewSet,
                    base_name='extension-queue')

# Router for children of /extensions/extension/{extension_pk}/.
sub_extensions = NestedSimpleRouter(
    extensions, r'extension', lookup='extension')
sub_extensions.register(r'versions', ExtensionVersionViewSet,
                        base_name='extension-version')


urlpatterns = patterns(
    '',
    url(r'', include(extensions.urls)),
    url(r'', include(sub_extensions.urls)),
    url(r'search/$', ExtensionSearchView.as_view(), name='extension-search'),
)
