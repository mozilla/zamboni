from rest_framework.routers import SimpleRouter

from mkt.extensions.views import ExtensionViewSet, ValidationViewSet

extensions = SimpleRouter()
extensions.register(r'validation', ValidationViewSet,
                    base_name='extension-validation')
extensions.register(r'extension', ExtensionViewSet)
