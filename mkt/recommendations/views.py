from django.conf import settings

import commonware.log
import requests
from django_statsd.clients import statsd
from requests.exceptions import RequestException, Timeout
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from mkt.api.authentication import (RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.base import CORSMixin, MarketplaceView
from mkt.search.filters import (DeviceTypeFilter, ProfileFilter,
                                PublicContentFilter, RegionFilter)
from mkt.search.views import SearchView
from mkt.webapps.indexers import WebappIndexer
from mkt.webapps.serializers import SimpleESAppSerializer


log = commonware.log.getLogger('z.recommendations')


class RecommendationView(CORSMixin, MarketplaceView, ListAPIView):
    cors_allowed_methods = ['get']
    authentication_classes = [RestSharedSecretAuthentication,
                              RestOAuthAuthentication]
    permission_classes = [AllowAny]
    serializer_class = SimpleESAppSerializer
    filter_backends = [PublicContentFilter, DeviceTypeFilter, RegionFilter,
                       ProfileFilter]

    def _popular(self):
        return SearchView.as_view()(self.request)

    def get_queryset(self):
        return WebappIndexer.search()

    def list(self, request, *args, **kwargs):
        if (not settings.RECOMMENDATIONS_ENABLED or
                not settings.RECOMMENDATIONS_API_URL or
                not self.request.user.is_authenticated()):
            return self._popular()
        else:
            app_ids = []
            url = '{base_url}/api/v2/recommend/{limit}/{user_hash}/'.format(
                base_url=settings.RECOMMENDATIONS_API_URL,
                limit=20, user_hash=self.request.user.recommendation_hash)

            try:
                with statsd.timer('recommendation.get'):
                    resp = requests.get(
                        url, timeout=settings.RECOMMENDATIONS_API_TIMEOUT)
                if resp.status_code == 200:
                    app_ids = resp.json()['recommendations']
            except Timeout as e:
                log.warning(u'Recommendation timeout: {error}'.format(error=e))
            except RequestException as e:
                # On recommendation API exceptions we return popular.
                log.error(u'Recommendation exception: {error}'.format(error=e))

            if not app_ids:
                # Fall back to a popularity search.
                return self._popular()

            # Get list of installed apps and remove from app_ids.
            installed = list(
                request.user.installed_set.values_list('addon_id', flat=True))
            app_ids = filter(lambda a: a not in installed, app_ids)

            queryset = self.filter_queryset(self.get_queryset())
            queryset = WebappIndexer.filter_by_apps(app_ids, queryset)

            return Response({
                'objects': self.serializer_class(
                    queryset.execute().hits, many=True,
                    context={'request': self.request}).data})
