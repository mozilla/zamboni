from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from waffle import switch_is_active
from waffle.models import Switch

from mkt.account.views import user_relevant_apps
from mkt.api.authentication import (RestAnonymousAuthentication,
                                    RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.base import CORSMixin
from mkt.collections.views import CollectionViewSet as BaseCollectionViewSet
from mkt.fireplace.serializers import (FireplaceAppSerializer,
                                       FireplaceCollectionSerializer,
                                       FireplaceESAppSerializer)
from mkt.search.views import FeaturedSearchView as BaseFeaturedSearchView
from mkt.search.views import SearchView as BaseSearchView
from mkt.site.helpers import fxa_auth_info
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

        # List of active switch names.
        switches = [str(s) for s in
                    Switch.objects.filter(active=True)
                    .values_list('name', flat=True)]

        data = {
            'region': request.REGION.slug,
            'waffle': {
                'switches': switches,
            }
        }
        if request.user.is_authenticated():
            data['apps'] = user_relevant_apps(request.user)
        if switch_is_active('firefox-accounts'):
            data['fxa_auth_state'], data['fxa_auth_url'] = fxa_auth_info()

        # Return an HttpResponse directly to be as fast as possible.
        return Response(data)
