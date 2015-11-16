from mkt.search.views import (
    SearchView as BaseSearchView,
    MultiSearchView as BaseMultiSearchView)
from mkt.tvplace.serializers import (TVAppSerializer,
                                     TVESAppSerializer,
                                     TVESWebsiteSerializer)
from mkt.webapps.views import AppViewSet as BaseAppViewset


class AppViewSet(BaseAppViewset):
    serializer_class = TVAppSerializer


class SearchView(BaseSearchView):
    serializer_class = TVESAppSerializer


class MultiSearchView(BaseMultiSearchView):
    serializer_classes = {
        'webapp': TVESAppSerializer,
        'website': TVESWebsiteSerializer,
    }
