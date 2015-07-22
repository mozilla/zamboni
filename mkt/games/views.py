from mkt.fireplace.views import MultiSearchView
from mkt.games.filters import DailyGamesFilter
from mkt.games.paginator import ESGameAggregationPaginator
from mkt.games.serializers import (GamesESAppSerializer,
                                   GamesESWebsiteSerializer)
from mkt.search.filters import DeviceTypeFilter, PublicAppsFilter


class DailyGamesView(MultiSearchView):
    filter_backends = [PublicAppsFilter, DeviceTypeFilter, DailyGamesFilter]
    paginator_class = ESGameAggregationPaginator

    def get_serializer_context(self):
        context = super(MultiSearchView, self).get_serializer_context()
        context['serializer_classes'] = {
            'webapp': GamesESAppSerializer,
            'website': GamesESWebsiteSerializer
        }
        return context
