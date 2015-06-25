from django.conf import settings

import commonware.log
from django_statsd.clients import statsd

from lib.geoip import GeoIP

import mkt
from mkt.regions.utils import parse_region

log = commonware.log.getLogger('mkt.regions')


class RegionMiddleware(object):
    """Figure out the user's region and set request.REGION accordingly, storing
    it on the request.user if there is one.

    - Outside the API, we automatically set RESTOFWORLD.
    - In the API, it tries to find a valid region in the query parameters,
      additionnally falling back to GeoIP for API v1 (for later versions we
      never do GeoIP automatically)."""

    def __init__(self):
        self.geoip = GeoIP(settings)

    def store_region(self, request, user_region):
        request.REGION = user_region
        mkt.regions.set_region(user_region)

    def region_from_request(self, request):
        address = request.META.get('REMOTE_ADDR')
        ip_reg = self.geoip.lookup(address)
        log.info('Geodude lookup for {0} returned {1}'
                 .format(address, ip_reg))
        return parse_region(ip_reg) or mkt.regions.RESTOFWORLD

    def process_request(self, request):
        regions = mkt.regions.REGION_LOOKUP
        user_region = restofworld = mkt.regions.RESTOFWORLD

        if not getattr(request, 'API', False):
            request.REGION = restofworld
            mkt.regions.set_region(restofworld)
            return

        # Try 'region' in POST/GET data first, if it's not there try geoip.
        url_region = request.GET.get('region')
        if url_region in regions:
            statsd.incr('z.regions.middleware.source.url')
            user_region = regions[url_region]
            log.info('Region {0} specified in URL; region set as {1}'
                     .format(url_region, user_region.slug))
        elif getattr(request, 'API_VERSION', None) == 1:
            # Fallback to GeoIP, but only for API version 1.
            statsd.incr('z.regions.middleware.source.geoip')
            user_region = self.region_from_request(request)
            log.info('Region not specified in URL; region set as {0}'
                     .format(user_region.slug))

        # Update the region on the user object if it changed.
        if (request.user.is_authenticated() and
                request.user.region != user_region.slug):
            request.user.region = user_region.slug
            request.user.save()

        # Persist the region on the request / local thread.
        self.store_region(request, user_region)
