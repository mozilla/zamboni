import json

from django.http import HttpResponse
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import AllowAny

from mkt.account.views import user_relevant_apps
from mkt.api.base import CORSMixin
from mkt.api.authentication import (RestAnonymousAuthentication,
                                    RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)

from mkt.collections.views import CollectionViewSet as BaseCollectionViewSet
from mkt.fireplace.serializers import (FireplaceCollectionSerializer, FireplaceAppSerializer,
                                      FireplaceESAppSerializer)
from mkt.search.views import (FeaturedSearchView as BaseFeaturedSearchView,
                              SearchView as BaseSearchView)
from mkt.webapps.views import AppViewSet as BaseAppViewset


class CollectionViewSet(BaseCollectionViewSet):
    serializer_class = FireplaceCollectionSerializer

    def get_serializer_context(self):
        """Context passed to the serializer. Since we are in Fireplace, we
        always want to use ES to fetch apps."""
        context = super(CollectionViewSet, self).get_serializer_context()
        context['use-es-for-apps'] = not self.request.GET.get('preview')
        return context


class AppViewSet(BaseAppViewset):
    serializer_class = FireplaceAppSerializer


class FeaturedSearchView(BaseFeaturedSearchView):
    serializer_class = FireplaceESAppSerializer
    collections_serializer_class = FireplaceCollectionSerializer
    authentication_classes = []


class SearchView(BaseSearchView):
    serializer_class = FireplaceESAppSerializer


class ConsumerInfoView(CORSMixin, RetrieveAPIView):
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]
    cors_allowed_methods = ['get']
    permission_classes = (AllowAny,)

    def retrieve(self, request, *args, **kwargs):
        data = {
            'region': request.REGION.slug
        }
        if request.amo_user:
          data['apps'] = user_relevant_apps(request.amo_user)

        # Return an HttpResponse directly to be as fast as possible.
        return HttpResponse(json.dumps(data),
                            content_type='application/json; charset=utf-8')
