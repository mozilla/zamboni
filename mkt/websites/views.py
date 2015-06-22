from lxml.etree import XMLSyntaxError

from django.db.transaction import non_atomic_requests

import requests
from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from mkt.api.authentication import (RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.authorization import GroupPermission
from mkt.api.base import CORSMixin, MarketplaceView
from mkt.api.paginator import ESPaginator
from mkt.reviewers.forms import ReviewersWebsiteSearchForm
from mkt.search.filters import (PublicAppsFilter, WebsiteSearchFormFilter,
                                RegionFilter, ReviewerWebsiteSearchFormFilter,
                                SearchQueryFilter, SortingFilter)
from mkt.search.forms import SimpleSearchForm
from mkt.websites.helpers import WebsiteMetadata
from mkt.websites.indexers import WebsiteIndexer
from mkt.websites.models import Website
from mkt.websites.serializers import (ESWebsiteSerializer,
                                      ReviewerESWebsiteSerializer,
                                      WebsiteSerializer)


class WebsiteView(CORSMixin, MarketplaceView, RetrieveAPIView):
    cors_allowed_methods = ['get']
    authentication_classes = [RestSharedSecretAuthentication,
                              RestOAuthAuthentication]
    permission_classes = [AllowAny]
    serializer_class = WebsiteSerializer
    queryset = Website.objects.valid()


class WebsiteSearchView(CORSMixin, MarketplaceView, ListAPIView):
    """
    Base website search view based on a single-string query.
    """
    cors_allowed_methods = ['get']
    authentication_classes = [RestSharedSecretAuthentication,
                              RestOAuthAuthentication]
    permission_classes = [AllowAny]
    filter_backends = [PublicAppsFilter, WebsiteSearchFormFilter, RegionFilter,
                       SearchQueryFilter, SortingFilter]
    serializer_class = ESWebsiteSerializer
    paginator_class = ESPaginator
    form_class = SimpleSearchForm

    def get_queryset(self):
        return WebsiteIndexer.search()

    @classmethod
    def as_view(cls, **kwargs):
        # Make all search views non_atomic: they should not need the db, or
        # at least they should not need to make db writes, so they don't need
        # to be wrapped in transactions.
        view = super(WebsiteSearchView, cls).as_view(**kwargs)
        return non_atomic_requests(view)


class ReviewersWebsiteSearchView(WebsiteSearchView):
    permission_classes = [GroupPermission('Apps', 'Review')]
    filter_backends = [SearchQueryFilter, ReviewerWebsiteSearchFormFilter,
                       SortingFilter]
    serializer_class = ReviewerESWebsiteSerializer
    form_class = ReviewersWebsiteSearchForm


class WebsiteMetadataScraperView(CORSMixin, MarketplaceView, APIView):
    """
    Base website search view based on a single-string query.
    """
    cors_allowed_methods = ['get']
    authentication_classes = [RestSharedSecretAuthentication,
                              RestOAuthAuthentication]
    permission_classes = [AllowAny]

    errors = {
        'no_url': '`url` querystring parameter required',
        'network': 'Unable to fetch website metadata',
        'malformed_data': 'Unable to parse website HTML.'
    }

    def get(self, request, format=None):
        url = request.QUERY_PARAMS.get('url', None)
        if not url:
            return Response(self.errors['no_url'],
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            return Response(WebsiteMetadata(url), status=status.HTTP_200_OK)
        except requests.exceptions.RequestException:
            return Response(self.errors['network'],
                            status=status.HTTP_400_BAD_REQUEST)
        except XMLSyntaxError:
            return Response(self.errors['malformed_data'],
                            status=status.HTTP_400_BAD_REQUEST)
