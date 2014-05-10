from rest_framework import routers

from .views import VersionViewSet

router = routers.DefaultRouter()
router.register(r'versions', VersionViewSet)
urlpatterns = router.urls
