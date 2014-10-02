from __future__ import absolute_import

import json

from django.conf import settings
from django.http import HttpResponse
from django.utils import translation

from elasticsearch_dsl import query
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

import amo
from mkt.access import acl
from mkt.api.authentication import (RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.base import CORSMixin, form_errors, MarketplaceView
from mkt.api.paginator import ESPaginator
from mkt.search.forms import ApiSearchForm, TARAKO_CATEGORIES_MAPPING
from mkt.translations.helpers import truncate
from mkt.webapps.indexers import WebappIndexer
from mkt.webapps.serializers import (ESAppSerializer, RocketbarESAppSerializer,
                                     RocketbarESAppSerializerV2,
                                     SuggestionsESAppSerializer)


DEFAULT_SORTING = {
    'popularity': '-popularity',
    # TODO: Should popularity replace downloads?
    'downloads': '-weekly_downloads',
    'rating': '-bayesian_rating',
    'created': '-created',
    'reviewed': '-reviewed',
    'name': 'name_sort',
}


def _get_locale_analyzer():
    analyzer = amo.SEARCH_LANGUAGE_TO_ANALYZER.get(translation.get_language())
    if not settings.ES_USE_PLUGINS and analyzer in amo.SEARCH_ANALYZER_PLUGINS:
        return None
    return analyzer


def get_custom_analyzer(language):
    """
    Returns name of analyzer based on language name.
    """
    if language in amo.STEMMER_MAP:
        return '%s_analyzer' % language
    return language


def name_query(q):
    """
    Returns a boolean should query `elasticsearch_dsl.query.Bool` given a
    query string.
    """
    should = []

    rules = {
        query.Match: {'query': q, 'boost': 3, 'analyzer': 'standard'},
        query.Match: {'query': q, 'boost': 4, 'type': 'phrase', 'slop': 1},
        query.Prefix: {'value': q, 'boost': 1.5}
    }
    # Only add fuzzy queries if q is a single word. It doesn't make sense to do
    # a fuzzy query for multi-word queries.
    if ' ' not in q:
        rules[query.Fuzzy] = {'value': q, 'boost': 2, 'prefix_length': 1}

    for k, v in rules.iteritems():
        for field in ('name', 'app_slug', 'author'):
            should.append(k(**{field: v}))

    # Exact matches need to be queried against a non-analyzed field. Let's do a
    # term query on `name_sort` for an exact match against the app name and
    # give it a good boost since this is likely what the user wants.
    should.append(query.Term(name_sort={'value': q, 'boost': 10}))

    analyzer = _get_locale_analyzer()
    if analyzer:
        should.append(query.Match(
            **{'name_%s' % analyzer: {'query': q, 'boost': 2.5}}))

    # Add searches on the description field.
    should.append(query.Match(
        description={'query': q, 'boost': 0.8, 'type': 'phrase'}))

    analyzer = _get_locale_analyzer()
    if analyzer:
        should.append(query.Match(
            **{'description_%s' % analyzer: {
                'query': q, 'boost': 0.6, 'type': 'phrase',
                'analyzer': get_custom_analyzer(analyzer)}}))

    # Add searches on tag field.
    should.append(query.Match(tags={'query': q}))
    if ' ' not in q:
        should.append(query.Fuzzy(tags={'value': q, 'prefix_length': 1}))

    return query.Bool(should=should)


def _sort_search(request, sq, data):
    """
    Sort webapp search based on query + region.

    data -- form data.
    """
    from mkt.api.base import get_region_from_request

    # When querying we want to sort by relevance. If no query is provided,
    # i.e. we are only applying filters which don't affect the relevance,
    # we sort by popularity descending.
    order_by = [] if request.GET.get('q') else ['-popularity']

    if data.get('sort'):
        region = get_region_from_request(request)
        if 'popularity' in data['sort'] and region and not region.adolescent:
            # Mature regions sort by their popularity field.
            order_by = ['-popularity_%s' % region.id]
        else:
            order_by = [DEFAULT_SORTING[name] for name in data['sort']
                        if name in DEFAULT_SORTING]

    if order_by:
        sq = sq.sort(*order_by)
    return sq


def search_form_to_es_fields(form_data):
    """
    Translate form field names to ES field names. Also used in Reviewers
    search.
    """
    return {
        'app_type': form_data['app_type'],
        'category': form_data['cat'],
        'author.raw': form_data['author'],
        'device': form_data['device'],
        'is_offline': form_data['offline'],
        'manifest_url': form_data['manifest_url'],
        'premium_type': form_data['premium_types'],
        'q': form_data['q'],
        'supported_locales': form_data['languages'],
        'tags': form_data['tag'],
    }


class SearchView(CORSMixin, MarketplaceView, GenericAPIView):
    """
    Base app search view based on a single-string query.
    """
    cors_allowed_methods = ['get']
    authentication_classes = [RestSharedSecretAuthentication,
                              RestOAuthAuthentication]
    permission_classes = [AllowAny]
    serializer_class = ESAppSerializer
    form_class = ApiSearchForm
    paginator_class = ESPaginator

    def search(self, request):
        """
        Takes a request (expecting request.GET.q), and returns the serializer
        and search query.
        """
        # Parse form.
        form = self.form_class(request.GET if request else None)
        if not form.is_valid():
            raise form_errors(form)
        form_data = form.cleaned_data

        # Query and filter.
        no_filter = (
            request.GET.get('filtering', '1') == '0' and
            acl.action_allowed(request, 'Feed', 'Curate'))
        sq = WebappIndexer.get_app_filter(
            request, search_form_to_es_fields(form_data), no_filter=no_filter)

        # Sort.
        sq = _sort_search(request, sq, form_data)

        # Done.
        page = self.paginate_queryset(sq)
        return self.get_pagination_serializer(page), form_data.get('q', '')

    def get(self, request):
        serializer, _ = self.search(request)
        return Response(serializer.data)


class FeaturedSearchView(SearchView):
    def get(self, request, *args, **kwargs):
        serializer, _ = self.search(request)
        data = self.add_featured_etc(request, serializer.data)
        response = Response(data)
        return response

    def add_featured_etc(self, request, data):
        # This endpoint used to return rocketfuel collections data but
        # rocketfuel is not used anymore now that we have the feed. To keep
        # backwards-compatibility we return empty arrays for the 3 keys that
        # contained rocketfuel data.
        data['collections'] = []
        data['featured'] = []
        data['operator'] = []
        return data


class SuggestionsView(SearchView):
    cors_allowed_methods = ['get']
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = SuggestionsESAppSerializer

    def get(self, request, *args, **kwargs):
        results, query = self.search(request)

        names = []
        descs = []
        urls = []
        icons = []

        for base_data in results.data['objects']:
            names.append(base_data['name'])
            descs.append(truncate(base_data['description']))
            urls.append(base_data['absolute_url'])
            icons.append(base_data['icon'])
        # This results a list. Usually this is a bad idea, but we don't return
        # any user-specific data, it's fully anonymous, so we're fine.
        return HttpResponse(json.dumps([query, names, descs, urls, icons]),
                            content_type='application/x-suggestions+json')


class RocketbarView(SearchView):
    cors_allowed_methods = ['get']
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = RocketbarESAppSerializer

    def get(self, request, *args, **kwargs):
        limit = request.GET.get('limit', 5)
        es_query = {
            'apps': {
                'completion': {'field': 'name_suggest', 'size': limit},
                'text': request.GET.get('q', '').strip()
            }
        }

        results = WebappIndexer.get_es().suggest(
            body=es_query, index=WebappIndexer.get_index())

        if 'apps' in results:
            data = results['apps'][0]['options']
        else:
            data = []
        serializer = self.get_serializer(data)
        # This returns a JSON list. Usually this is a bad idea for security
        # reasons, but we don't include any user-specific data, it's fully
        # anonymous, so we're fine.
        return HttpResponse(json.dumps(serializer.data),
                            content_type='application/x-rocketbar+json')


class RocketbarViewV2(RocketbarView):
    serializer_class = RocketbarESAppSerializerV2
