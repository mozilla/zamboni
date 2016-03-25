from __future__ import absolute_import

import json

from django.db.transaction import non_atomic_requests
from django.http import HttpResponse
from django.utils.functional import lazy

from elasticsearch_dsl import filter as es_filter
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

import mkt
from mkt.api.authentication import (RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.base import CORSMixin, MarketplaceView
from mkt.api.permissions import AnyOf, GroupPermission
from mkt.extensions import indexers as e_indexers
from mkt.extensions.serializers import ESExtensionSerializer
from mkt.operators.permissions import IsOperatorPermission
from mkt.search.forms import ApiSearchForm, COLOMBIA_WEBSITE
from mkt.search.indexers import BaseIndexer
from mkt.search.filters import (DeviceTypeFilter, HomescreenFilter,
                                OpenMobileACLFilter, ProfileFilter,
                                PublicContentFilter, PublicSearchFormFilter,
                                RegionFilter, SearchQueryFilter, SortingFilter,
                                ValidAppsFilter)
from mkt.search.serializers import DynamicSearchSerializer
from mkt.search.utils import Search
from mkt.translations.helpers import truncate
from mkt.webapps import indexers
from mkt.webapps.serializers import (ESAppSerializer, RocketbarESAppSerializer,
                                     RocketbarESAppSerializerV2,
                                     SuggestionsESAppSerializer)
from mkt.websites import indexers as ws_indexers
from mkt.websites.serializers import ESWebsiteSerializer


class SearchView(CORSMixin, MarketplaceView, ListAPIView):
    """
    Base app search view based on a single-string query.
    """
    cors_allowed_methods = ['get']
    authentication_classes = [RestSharedSecretAuthentication,
                              RestOAuthAuthentication]
    permission_classes = [AllowAny]
    filter_backends = [DeviceTypeFilter, HomescreenFilter, ProfileFilter,
                       PublicContentFilter, PublicSearchFormFilter,
                       RegionFilter, SearchQueryFilter, SortingFilter]

    serializer_class = ESAppSerializer
    form_class = ApiSearchForm

    def get_queryset(self):
        return indexers.WebappIndexer.search()

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
    # mapping_names_and_indices is lazy because our tests modify the indices
    # to use test indices. So we want it to be instantiated only when we start
    # using it in the code, not before.
    mapping_names_and_indices = lazy(lambda: {
        'extension': {
            'doc_type': e_indexers.ExtensionIndexer.get_mapping_type_name(),
            'index': e_indexers.ExtensionIndexer.get_index()
        },
        'webapp': {
            'doc_type': indexers.WebappIndexer.get_mapping_type_name(),
            'index': indexers.WebappIndexer.get_index(),
        },
        'homescreen': {
            'doc_type': indexers.HomescreenIndexer.get_mapping_type_name(),
            'index': indexers.HomescreenIndexer.get_index(),
        },

        'website': {
            'doc_type': ws_indexers.WebsiteIndexer.get_mapping_type_name(),
            'index': ws_indexers.WebsiteIndexer.get_index()
        }
    }, dict)()
    serializer_classes = {
        'extension': ESExtensionSerializer,
        'webapp': ESAppSerializer,
        'homescreen': ESAppSerializer,
        'website': ESWebsiteSerializer
    }

    @classmethod
    def get_default_indices(cls):
        return [
            cls.mapping_names_and_indices['webapp'],
            cls.mapping_names_and_indices['website'],
        ]

    def get_doc_types_and_indices(self):
        """
        Return a dict with the index and doc_type keys to use for this request,
        using the 'doc_type' GET parameter.

        Valid `doc_type` parameters: 'extension', 'webapp' and 'website'. If
        no parameter is passed or the value is not recognized, default to
        'webapp', 'website'."""
        cls = self.__class__
        requested_doc_types = self.request.GET.get('doc_type', '').split(',')
        filtered_names_and_indices = [
            cls.mapping_names_and_indices[key] for key
            in cls.mapping_names_and_indices if key in requested_doc_types]
        if not filtered_names_and_indices:
            # Default is to include only webapp and website for now.
            filtered_names_and_indices = cls.get_default_indices()
        # Now regroup to produce a dict with doc_type: [...], index: [...].
        return {key: [item[key] for item in filtered_names_and_indices]
                for key in ['doc_type', 'index']}

    def get_serializer_context(self):
        # This context is then used by the DynamicSearchSerializer to switch
        # serializer depending on the document being serialized.
        cls = self.__class__
        context = super(MultiSearchView, self).get_serializer_context()
        context['serializer_classes'] = cls.serializer_classes
        return context

    def _get_colombia_filter(self):
        if self.allow_colombia and self.request.REGION == mkt.regions.COL:
            return None
        co_filter = es_filter.Term(tags=COLOMBIA_WEBSITE)
        return es_filter.F(es_filter.Bool(must_not=[co_filter]),)

    def get_queryset(self):
        excluded_fields = list(set(indexers.WebappIndexer.hidden_fields +
                                   ws_indexers.WebsiteIndexer.hidden_fields +
                                   e_indexers.ExtensionIndexer.hidden_fields))
        co_filters = self._get_colombia_filter()
        qs = (Search(using=BaseIndexer.get_es(),
                     **self.get_doc_types_and_indices())
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

        results = indexers.WebappIndexer.get_es().suggest(
            body=es_query, index=indexers.WebappIndexer.get_index())

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
