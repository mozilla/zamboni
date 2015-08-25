from mkt.fireplace.views import MultiSearchView
from mkt.games.filters import DailyGamesFilter
from mkt.games.paginator import ESGameAggregationPaginator
from mkt.search.filters import DeviceTypeFilter, PublicContentFilter


class DailyGamesView(MultiSearchView):
    filter_backends = [PublicContentFilter, DeviceTypeFilter, DailyGamesFilter]
    paginator_class = ESGameAggregationPaginator
