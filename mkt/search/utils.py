from math import log10

from django.core.exceptions import ObjectDoesNotExist

from elasticsearch_dsl.search import Search as dslSearch
from statsd import statsd

from mkt.constants.base import VALID_STATUSES


BOOST_MULTIPLIER_FOR_PUBLIC_CONTENT = 4.0


class Search(dslSearch):

    def execute(self):
        with statsd.timer('search.execute'):
            results = super(Search, self).execute()
            statsd.timing('search.took', results.took)
            return results


def _property_value_by_region(obj, region=None, property=None):
    if obj.is_dummy_content_for_qa():
        # Apps and Websites set up by QA for testing should never be considered
        # popular or trending.
        return 0

    if region and not region.adolescent:
        by_region = region.id
    else:
        by_region = 0

    try:
        return getattr(obj, property).get(region=by_region).value
    except ObjectDoesNotExist:
        return 0


def get_popularity(obj, region=None):
    """
    Returns popularity value for the given obj to use in Elasticsearch.

    If no region, uses global value.
    If region and region is not mature, uses global value.
    Otherwise uses regional popularity value.

    """
    return _property_value_by_region(obj, region=region, property='popularity')


def get_trending(obj, region=None):
    """
    Returns trending value for the given obj to use in Elasticsearch.

    If no region, uses global value.
    If region and region is not mature, uses global value.
    Otherwise uses regional popularity value.

    """
    return _property_value_by_region(obj, region=region, property='trending')


def get_boost(obj):
    """
    Returns the boost used in Elasticsearch for this app.

    The boost is based on a few factors, the most important is number of
    installs. We use log10 so the boost doesn't completely overshadow any
    other boosting we do at query time.
    """
    boost = max(log10(1 + get_popularity(obj)), 1.0)

    # We give a little extra boost to approved apps.
    if obj.status in VALID_STATUSES:
        boost *= BOOST_MULTIPLIER_FOR_PUBLIC_CONTENT

    return boost
