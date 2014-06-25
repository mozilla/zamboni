from __future__ import absolute_import

import json

from django.conf import settings
from django.http import HttpResponse
from django.utils import translation

from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

import amo
from mkt.api.authentication import (RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.base import CORSMixin, form_errors, MarketplaceView
from mkt.api.paginator import ESPaginator
from mkt.collections.constants import (COLLECTIONS_TYPE_BASIC,
                                       COLLECTIONS_TYPE_FEATURED,
                                       COLLECTIONS_TYPE_OPERATOR)
from mkt.collections.filters import CollectionFilterSetWithFallback
from mkt.collections.models import Collection
from mkt.collections.serializers import CollectionSerializer
from mkt.features.utils import get_feature_profile
from mkt.search.forms import ApiSearchForm, TARAKO_CATEGORIES_MAPPING
from mkt.search.serializers import (ESAppSerializer, RocketbarESAppSerializer,
                                    SuggestionsESAppSerializer)
from mkt.search.utils import S
from mkt.translations.helpers import truncate
from mkt.webapps.indexers import WebappIndexer
from mkt.webapps.models import Webapp


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


def name_only_query(q):
    """
    Returns a dictionary with field/value mappings to pass to elasticsearch.

    This sets up various queries with boosting against the name field in the
    elasticsearch index.

    """
    d = {}

    rules = {
        'match': {'query': q, 'boost': 3, 'analyzer': 'standard'},
        'match': {'query': q, 'boost': 4, 'type': 'phrase', 'slop': 1},
        'startswith': {'value': q, 'boost': 1.5}
    }

    # Only add fuzzy queries if q is a single word. It doesn't make sense to do
    # a fuzzy query for multi-word queries.
    if ' ' not in q:
        rules['fuzzy'] = {'value': q, 'boost': 2, 'prefix_length': 1}

    for k, v in rules.iteritems():
        for field in ('name', 'app_slug', 'author'):
            d['%s__%s' % (field, k)] = v

    # Exact matches need to be queried against a non-analyzed field. Let's do a
    # term query on `name_sort` for an exact match against the app name and
    # give it a good boost since this is likely what the user wants.
    d['name_sort__term'] = {'value': q, 'boost': 10}

    analyzer = _get_locale_analyzer()
    if analyzer:
        d['name_%s__match' % analyzer] = {
            'query': q, 'boost': 2.5,
            'analyzer': get_custom_analyzer(analyzer)}
    return d


def name_query(q):
    """
    Returns a dictionary with field/value mappings to pass to elasticsearch.

    Note: This is marketplace specific. See apps/search/views.py for AMO.

    """
    more = {
        'description__match': {'query': q, 'boost': 0.8, 'type': 'phrase'},
    }

    analyzer = _get_locale_analyzer()
    if analyzer:
        more['description_%s__match' % analyzer] = {
            'query': q, 'boost': 0.6, 'type': 'phrase',
            'analyzer': get_custom_analyzer(analyzer)}

    more['tags__match'] = {'query': q}
    if ' ' not in q:
        more['tags__fuzzy'] = {'value': q, 'prefix_length': 1}

    return dict(more, **name_only_query(q))


def _filter_search(request, qs, data, region=None, profile=None):
    """
    Filter an ES queryset based on a list of filters.

    If `profile` (a FeatureProfile object) is provided we filter by the
    profile. If you don't want to filter by these don't pass it. I.e. do the
    device detection for when this happens elsewhere.

    """
    # An empty `order_by` will result in a sort by relevance, the default for
    # Elasticsearch.
    order_by = []

    # Queries.
    if data.get('q'):
        qs = qs.query(should=True, **name_query(data['q'].lower()))
    else:
        # When querying we want to sort by relevance. If no query is provided,
        # i.e. we are only applying filters which don't affect the relevance,
        # we sort by popularity descending.
        order_by = ['-popularity']

    # Filters.
    filters = {
        'category__in': data.get('cat', []),
        # We only allow searching on one tag for now, and not a list.
        'tags': data.get('tag'),
        'device': data.get('device'),
        'premium_type__in': data.get('premium_types', []),
        'app_type__in': data.get('app_type', []),
        'manifest_url': data.get('manifest_url'),
        'supported_locales__in': data.get('languages', []),
    }
    # Remove filters with no values.
    for k, v in filters.items():
        if not v:
            filters.pop(k)
    # Handle the NullBooleanField.
    if data.get('offline') in (True, False):
        filters['is_offline'] = data['offline']
    qs = qs.filter(**filters)

    if profile:
        # Exclude apps that require any features we don't support.
        qs = qs.filter(**profile.to_kwargs(prefix='features.has_'))

    # Sorting.
    if data.get('sort'):
        if 'popularity' in data['sort'] and region and not region.adolescent:
            # Mature regions sort by their popularity field.
            order_by = ['-popularity_%s' % region.id]
        else:
            order_by = [DEFAULT_SORTING[name] for name in data['sort']
                        if name in DEFAULT_SORTING]
    if order_by:
        qs = qs.order_by(*order_by)

    return qs


class SearchView(CORSMixin, MarketplaceView, GenericAPIView):
    cors_allowed_methods = ['get']
    authentication_classes = [RestSharedSecretAuthentication,
                              RestOAuthAuthentication]
    permission_classes = [AllowAny]
    serializer_class = ESAppSerializer
    form_class = ApiSearchForm
    paginator_class = ESPaginator

    def search(self, request):
        form_data = self.get_search_data(request)
        query = form_data.get('q', '')
        base_filters = {'type': form_data['type']}

        qs = self.get_query(request, base_filters=base_filters,
                            region=self.get_region_from_request(request))
        profile = get_feature_profile(request)
        qs = self.apply_filters(request, qs, data=form_data,
                                profile=profile)
        page = self.paginate_queryset(qs.values_dict())
        return self.get_pagination_serializer(page), query

    def get(self, request, *args, **kwargs):
        serializer, _ = self.search(request)
        return Response(serializer.data)

    def get_search_data(self, request):
        form = self.form_class(request.GET if request else None)
        if not form.is_valid():
            raise form_errors(form)
        return form.cleaned_data

    def get_query(self, request, base_filters=None, region=None):
        return Webapp.from_search(request, region=region, gaia=request.GAIA,
                                  mobile=request.MOBILE, tablet=request.TABLET,
                                  filter_overrides=base_filters)

    def apply_filters(self, request, qs, data=None, profile=None):
        # Build region filter.
        region = self.get_region_from_request(request)
        return _filter_search(request, qs, data, region=region,
                              profile=profile)


class FeaturedSearchView(SearchView):
    collections_serializer_class = CollectionSerializer

    def collections(self, request, collection_type=None, limit=1):
        filters = request.GET.dict()
        region = self.get_region_from_request(request)
        if region:
            filters.setdefault('region', region.slug)
        if collection_type is not None:
            qs = Collection.public.filter(collection_type=collection_type)
        else:
            qs = Collection.public.all()
        qs = CollectionFilterSetWithFallback(filters, queryset=qs).qs
        preview_mode = filters.get('preview', False)
        serializer = self.collections_serializer_class(
            qs[:limit], many=True, context={
                'request': request,
                'view': self,
                'use-es-for-apps': not preview_mode}
        )
        return serializer.data, getattr(qs, 'filter_fallback', None)

    def get(self, request, *args, **kwargs):
        serializer, _ = self.search(request)
        data, filter_fallbacks = self.add_featured_etc(request,
                                                       serializer.data)
        response = Response(data)
        for name, value in filter_fallbacks.items():
            response['API-Fallback-%s' % name] = ','.join(value)
        return response

    def add_featured_etc(self, request, data):
        # Tarako categories don't have collections.
        if request.GET.get('cat') in TARAKO_CATEGORIES_MAPPING:
            return data, {}
        types = (
            ('collections', COLLECTIONS_TYPE_BASIC),
            ('featured', COLLECTIONS_TYPE_FEATURED),
            ('operator', COLLECTIONS_TYPE_OPERATOR),
        )
        filter_fallbacks = {}
        for name, col_type in types:
            data[name], fallback = self.collections(request,
                                                    collection_type=col_type)
            if fallback:
                filter_fallbacks[name] = fallback

        return data, filter_fallbacks


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

        results = S(WebappIndexer).get_es().send_request(
            'GET', [WebappIndexer.get_index(), '_suggest'], body=es_query)

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
