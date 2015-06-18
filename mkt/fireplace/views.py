from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

import mkt.regions
from mkt.account.views import user_relevant_apps
from mkt.api.authentication import (RestAnonymousAuthentication,
                                    RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.base import CORSMixin
from mkt.fireplace.serializers import (FireplaceAppSerializer,
                                       FireplaceESAppSerializer,
                                       FireplaceESWebsiteSerializer)
from mkt.search.views import (
    SearchView as BaseSearchView,
    MultiSearchView as BaseMultiSearchView)
from mkt.webapps.views import AppViewSet as BaseAppViewset


class AppViewSet(BaseAppViewset):
    serializer_class = FireplaceAppSerializer


class SearchView(BaseSearchView):
    serializer_class = FireplaceESAppSerializer


class MultiSearchView(BaseMultiSearchView):
    def get_serializer_context(self):
        context = super(MultiSearchView, self).get_serializer_context()
        context['serializer_classes'] = {
            'webapp': FireplaceESAppSerializer,
            'website': FireplaceESWebsiteSerializer
        }
        return context


class ConsumerInfoView(CORSMixin, RetrieveAPIView):
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]
    cors_allowed_methods = ['get']
    permission_classes = (AllowAny,)

    def retrieve(self, request, *args, **kwargs):
        if (getattr(request, 'API_VERSION', None) > 1 and
                request.REGION == mkt.regions.RESTOFWORLD):
            # In API v2 and onwards, geoip is not done automatically, so we
            # need to do it ourselves.
            region_middleware = mkt.regions.middleware.RegionMiddleware()
            user_region = region_middleware.region_from_request(request)
            region_middleware.store_region(request, user_region)

        data = {
            'region': request.REGION.slug,
        }
        if request.user.is_authenticated():
            data['apps'] = user_relevant_apps(request.user)
            data['enable_recommendations'] = (
                request.user.enable_recommendations)

        # Return an HttpResponse directly to be as fast as possible.
        return Response(data)
