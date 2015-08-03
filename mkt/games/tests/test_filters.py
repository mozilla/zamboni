import datetime

from nose.tools import eq_

from mkt.games.constants import GAME_CATEGORIES
from mkt.games.filters import DailyGamesFilter
from mkt.games.views import DailyGamesView
from mkt.search.tests.test_filters import FilterTestsBase


class TestDailyGamesFilter(FilterTestsBase):
    filter_classes = [DailyGamesFilter]

    def setUp(self):
        super(TestDailyGamesFilter, self).setUp()
        self.view_class = DailyGamesView

    def test_filter(self):
        qs = self._filter(self.req)
        functions = qs['query']['function_score']['functions']
        shoulds = qs['query']['function_score']['filter']['bool']['should']

        # Test function.
        eq_(functions[0]['random_score']['seed'],
            int(datetime.datetime.now().strftime('%Y%m%d')))

        for i, cat in enumerate(GAME_CATEGORIES):
            # Test tags.
            eq_(shoulds[i]['term']['tags'], cat)
