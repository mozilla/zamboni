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
        shoulds = qs['query']['bool']['should']

        for i, cat in enumerate(GAME_CATEGORIES):
            # Test function.
            function_score = shoulds[i]['function_score']
            eq_(function_score['functions'][0]['random_score']['seed'],
                int(datetime.datetime.now().strftime('%Y%m%d')))

            # Test tags.
            must = function_score['filter']['bool']['must'][0]
            eq_(must['term']['tags'], cat)
