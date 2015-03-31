from django.db.transaction import non_atomic_requests

from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny

from mkt.api.authentication import (RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.base import CORSMixin, MarketplaceView
from mkt.api.paginator import ESPaginator
from mkt.websites.indexers import WebsiteIndexer
from mkt.websites.models import Website
from mkt.websites.serializers import ESWebsiteSerializer, WebsiteSerializer


class WebsiteView(CORSMixin, MarketplaceView, ListAPIView):
    cors_allowed_methods = ['get']
    authentication_classes = [RestSharedSecretAuthentication,
                              RestOAuthAuthentication]
    permission_classes = [AllowAny]
    serializer_class = WebsiteSerializer
    model = Website


class WebsiteSearchView(CORSMixin, MarketplaceView, ListAPIView):
    """
    Base website search view based on a single-string query.
    """
    cors_allowed_methods = ['get']
    authentication_classes = [RestSharedSecretAuthentication,
                              RestOAuthAuthentication]
    permission_classes = [AllowAny]
    filter_backends = []  # FIXME: SearchQueryFilter and friends.
    serializer_class = ESWebsiteSerializer
    paginator_class = ESPaginator

    def get_queryset(self):
        return WebsiteIndexer.search()

    @classmethod
    def as_view(cls, **kwargs):
        # Make all search views non_atomic: they should not need the db, or
        # at least they should not need to make db writes, so they don't need
        # to be wrapped in transactions.
        view = super(WebsiteSearchView, cls).as_view(**kwargs)
        return non_atomic_requests(view)
