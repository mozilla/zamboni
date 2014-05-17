from rest_framework import routers

from mkt.ratings.views import RatingViewSet


router = routers.DefaultRouter()
router.register(r'rating', RatingViewSet, base_name='ratings')
urlpatterns = router.urls
