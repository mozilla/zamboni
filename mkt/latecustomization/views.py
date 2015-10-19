from django.utils.datastructures import MultiValueDictKeyError

from rest_framework import mixins, permissions, viewsets
from rest_framework.exceptions import ParseError

from mpconstants.carriers import MOBILE_CODES

from mkt.api.authentication import (RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.base import CORSMixin, MarketplaceView
from mkt.access import acl
from mkt.constants.carriers import CARRIER_MAP
from mkt.constants.regions import REGIONS_DICT, REGIONS_BY_MCC
from mkt.feed.views import FeedShelfPermissionMixin, RegionCarrierFilter
from mkt.latecustomization.models import LateCustomizationItem
from mkt.latecustomization.serializers import LateCustomizationSerializer
from mkt.operators.models import OperatorPermission


class LateCustomizationPermission(permissions.BasePermission):
    """
    Pass for GET/HEAD/OPTIONS, or if the user has operator permissions for any
    carrier/region pair.
    """
    def has_permission(self, request, view):
        if (request.method in permissions.SAFE_METHODS or
                acl.action_allowed(request, 'OperatorDashboard', '*')):
            return True
        return OperatorPermission.user_is_operator(request.user)


class LateCustomizationViewSet(FeedShelfPermissionMixin, CORSMixin,
                               MarketplaceView, viewsets.GenericViewSet,
                               mixins.ListModelMixin, mixins.CreateModelMixin,
                               mixins.DestroyModelMixin):
    """
    Operations for late customization items.
    """
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication]

    permission_classes = [LateCustomizationPermission]
    serializer_class = LateCustomizationSerializer
    queryset = LateCustomizationItem.objects.all()
    filter_backends = [RegionCarrierFilter]
    cors_allowed_methods = ('get', 'post', 'delete')

    def get_carrier_region(self, request):
        data = self.req_data() or self.request.GET
        if 'region' in data and 'carrier' in data:
            carrier = data['carrier']
            region = data['region']
        elif 'mnc' in data and 'mcc' in data:
            try:
                carrier = MOBILE_CODES[int(data['mcc'])][int(data['mnc'])]
                region = REGIONS_BY_MCC[int(data['mcc'])]
            except (KeyError, ValueError):
                raise ParseError("Invalid mnc/mcc pair")
        else:
            raise ParseError("Both 'region' and 'carrier' or both "
                             "'mnc' and 'mcc' parameters must be provided")
        carrier = (carrier if isinstance(carrier, (int, long)) else
                   CARRIER_MAP[carrier].id)
        region = (region if isinstance(region, (int, long)) else
                  REGIONS_DICT[region].id)
        return carrier, region

    def list(self, request, *args, **kwargs):
        carrier, region = self.get_carrier_region(request)
        self.queryset = self.queryset.filter(region=region, carrier=carrier)
        return super(LateCustomizationViewSet, self).list(request, *args,
                                                          **kwargs)

    def create(self, request, *args, **kwargs):
        carrier, region = self.get_carrier_region(request)
        try:
            self.require_operator_permission(
                request.user, carrier, region)
        except (KeyError, MultiValueDictKeyError):
            raise ParseError(
                "Operator permission for this region/carrier required to add "
                "late-customization apps")
        return super(LateCustomizationViewSet, self).create(request, *args,
                                                            **kwargs)

    def pre_delete(self, obj):
        try:
            self.require_operator_permission(
                self.request.user, obj.carrier, obj.region)
        except (KeyError, MultiValueDictKeyError):
            raise ParseError(
                "Operator permission for this late-customization app's "
                "region/carrier required to remove it")
