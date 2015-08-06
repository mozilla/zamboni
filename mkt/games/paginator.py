from django.core.paginator import Page

from mkt.api.paginator import ESPaginator
from mkt.games.constants import GAME_CATEGORIES


class ESGameAggregationPaginator(ESPaginator):
    """
    Paginator that handles aggregated results using a hardcoded aggregation
    name and bucket name specified in mkt.games.filters. Doesn't really do
    any paginating, we're just using the Paginator to hijack the queryset
    execution such that we can still use DRF CBVs and not write big imperative
    views.

    Normally, the ESPaginator looks for results in execute().hits, this will
    look for results in execute().aggregations which follows a different
    format.

    Ideally, this class would be able to be configured with different
    aggregation and bucket names, but currently it's only used here.
    """
    def page(self, number):
        """
        Returns a page object.
        """
        # Don't fetch hits, only care about aggregations.
        self.object_list._params['search_type'] = 'count'
        result = self.object_list.execute()

        # Pull the results from the aggregations.
        hits = []
        aggs = result.aggregations
        buckets = aggs['top_hits']['buckets']
        for bucket in buckets:
            # Have to check the bucket key since other tags could get
            # aggregated (e.g., `featured-game`) when we only care about game
            # categories.
            if bucket['key'] in GAME_CATEGORIES:
                hits.append(bucket['first_game']['hits']['hits'][0])

        page = Page(hits, number, self)

        # Update the `_count`.
        self._count = len(page.object_list)

        return page
