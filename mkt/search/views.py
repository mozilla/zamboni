from __future__ import absolute_import

import json

from django.db.transaction import non_atomic_requests
from django.http import HttpResponse

from elasticsearch_dsl import filter as es_filter
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

import mkt
from mkt.api.authentication import (RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.base import CORSMixin, MarketplaceView
from mkt.api.paginator import ESPaginator
from mkt.api.permissions import AnyOf, GroupPermission
from mkt.operators.permissions import IsOperatorPermission
from mkt.search.forms import ApiSearchForm, COLOMBIA_WEBSITE
from mkt.search.indexers import BaseIndexer
from mkt.search.filters import (DeviceTypeFilter, OpenMobileACLFilter,
                                ProfileFilter, PublicContentFilter,
                                PublicSearchFormFilter, RegionFilter,
                                SearchQueryFilter, SortingFilter,
                                ValidAppsFilter)
from mkt.search.serializers import DynamicSearchSerializer
from mkt.search.utils import Search
from mkt.translations.helpers import truncate
from mkt.webapps.indexers import WebappIndexer
from mkt.webapps.serializers import (ESAppSerializer, RocketbarESAppSerializer,
                                     RocketbarESAppSerializerV2,
                                     SuggestionsESAppSerializer)
from mkt.websites.indexers import WebsiteIndexer
from mkt.websites.serializers import ESWebsiteSerializer


class SearchView(CORSMixin, MarketplaceView, ListAPIView):
    """
    Base app search view based on a single-string query.
    """
    cors_allowed_methods = ['get']
    authentication_classes = [RestSharedSecretAuthentication,
                              RestOAuthAuthentication]
    permission_classes = [AllowAny]
    filter_backends = [DeviceTypeFilter, ProfileFilter, PublicContentFilter,
                       PublicSearchFormFilter, RegionFilter, SearchQueryFilter,
                       SortingFilter]

    serializer_class = ESAppSerializer
    form_class = ApiSearchForm
    paginator_class = ESPaginator

    def get_queryset(self):
        return WebappIndexer.search()

    @classmethod
    def as_view(cls, **kwargs):
        # Make all search views non_atomic: they should not need the db, or
        # at least they should not need to make db writes, so they don't need
        # to be wrapped in transactions.
        view = super(SearchView, cls).as_view(**kwargs)
        return non_atomic_requests(view)


class MultiSearchView(SearchView):
    """
    Search View capable of returning multiple content types in the same
    results list (e.g., apps + sites). Can take a `doc_type` param to filter by
    `app`s only or `site`s only.
    """
    allow_colombia = False
    serializer_class = DynamicSearchSerializer

    def _get_doc_types(self):
        # Check if we are filtering by a doc_type (e.g., apps, sites).
        # Default to all content types.
        doc_type = self.request.GET.get('doc_type', 'all')
        app_doc = WebappIndexer.get_mapping_type_name()
        site_doc = WebsiteIndexer.get_mapping_type_name()
        if doc_type == 'webapp':
            return [app_doc]
        elif doc_type == 'website':
            return [site_doc]
        return [app_doc, site_doc]

    def _get_indices(self):
        # Check if we are filtering by a doc_type (e.g., apps, sites).
        # Default to all content types.
        doc_type = self.request.GET.get('doc_type', 'all')
        app_index = WebappIndexer.get_index()
        site_index = WebsiteIndexer.get_index()
        if doc_type == 'webapp':
            return [app_index]
        elif doc_type == 'website':
            return [site_index]
        return [app_index, site_index]

    def get_serializer_context(self):
        context = super(MultiSearchView, self).get_serializer_context()
        context['serializer_classes'] = {
            'webapp': ESAppSerializer,
            'website': ESWebsiteSerializer
        }
        return context

    def _get_colombia_filter(self):
        if self.allow_colombia and self.request.REGION == mkt.regions.COL:
            return None
        co_filter = es_filter.Term(tags=COLOMBIA_WEBSITE)
        return es_filter.F(es_filter.Bool(must_not=[co_filter]),)

    def get_queryset(self):
        excluded_fields = list(set(WebappIndexer.hidden_fields +
                                   WebsiteIndexer.hidden_fields))
        co_filters = self._get_colombia_filter()
        qs = (Search(using=BaseIndexer.get_es(),
                     index=self._get_indices(),
                     doc_type=self._get_doc_types())
              .extra(_source={'exclude': excluded_fields}))
        if co_filters:
            return qs.filter(co_filters)
        return qs


class FeaturedSearchView(SearchView):

    def list(self, request, *args, **kwargs):
        response = super(FeaturedSearchView, self).list(request, *args,
                                                        **kwargs)
        data = self.add_featured_etc(request, response.data)
        return Response(data)

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
    authentication_classes = []
    serializer_class = SuggestionsESAppSerializer

    def list(self, request, *args, **kwargs):
        query = request.GET.get('q', '')
        response = super(SuggestionsView, self).list(request, *args, **kwargs)

        names = []
        descs = []
        urls = []
        icons = []

        for base_data in response.data['objects']:
            names.append(base_data['name'])
            descs.append(truncate(base_data['description']))
            urls.append(base_data['absolute_url'])
            icons.append(base_data['icon'])
        # This results a list. Usually this is a bad idea, but we don't return
        # any user-specific data, it's fully anonymous, so we're fine.
        return HttpResponse(json.dumps([query, names, descs, urls, icons]),
                            content_type='application/x-suggestions+json')


class NonPublicSearchView(SearchView):
    """
    A search view that allows searching for apps with non-public statuses
    protected behind a permission class. Region exclusions still affects
    results.

    """
    authentication_classes = [RestSharedSecretAuthentication,
                              RestOAuthAuthentication]
    permission_classes = [GroupPermission('Feed', 'Curate')]
    filter_backends = [SearchQueryFilter, PublicSearchFormFilter,
                       ValidAppsFilter, DeviceTypeFilter, RegionFilter,
                       ProfileFilter, SortingFilter]


class NoRegionSearchView(SearchView):
    """
    A search view that allows searching for public apps regardless of region
    exclusions, protected behind a permission class.

    A special class is needed because when RegionFilter is included, as it is
    in the default SearchView, it will always use whatever region was set on
    the request, and we default to setting restofworld when no region is
    passed.

    """
    authentication_classes = [RestSharedSecretAuthentication,
                              RestOAuthAuthentication]
    permission_classes = [AnyOf(GroupPermission('Feed', 'Curate'),
                                GroupPermission('OperatorDashboard', '*'),
                                IsOperatorPermission)]
    filter_backends = [SearchQueryFilter, PublicSearchFormFilter,
                       PublicContentFilter, DeviceTypeFilter,
                       ProfileFilter, SortingFilter]


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


class OpenMobileACLSearchView(SearchView):
    """
    A search view designed to find all valid apps using the Openmobile ACL
    feature flag. Region exclusions are ignored. The consumer pages will use
    that to verify the user has at least one app installed that belongs to that
    list before trying to install an ACL.

    It returns a list of manifest URLs directly, without pagination.
    """
    filter_backends = [ValidAppsFilter, OpenMobileACLFilter]

    def get_queryset(self):
        qs = super(OpenMobileACLSearchView, self).get_queryset()
        return qs.extra(_source={'include': ['manifest_url']})

    def get(self, request, *args, **kwargs):
        hits = self.filter_queryset(self.get_queryset()).execute().hits
        data = [obj['manifest_url'] for obj in hits]

        # This returns a JSON list. Usually this is a bad idea for security
        # reasons, but we don't include any user-specific data, it's fully
        # anonymous, so we're fine.
        return HttpResponse(json.dumps(data),
                            content_type='application/json')
