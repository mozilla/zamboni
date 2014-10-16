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

    def _popular(self):
        return SearchView.as_view()(self.request)

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

            sq = WebappIndexer.get_app_filter(self.request, app_ids=app_ids)
            return Response({
                'objects': self.serializer_class(
                    sq.execute().hits, many=True,
                    context={'request': self.request}).data})
