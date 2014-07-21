from elasticsearch_dsl.search import Search as dslSearch
from statsd import statsd


class Search(dslSearch):

    def execute(self):
        with statsd.timer('search.execute'):
            results = super(Search, self).execute()
            statsd.timing('search.took', results['took'])
            return results
