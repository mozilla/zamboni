from django.utils.datastructures import MultiValueDictKeyError

from rest_framework import mixins, permissions, viewsets
from rest_framework.exceptions import ParseError

from mkt.api.authentication import (RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.base import CORSMixin, MarketplaceView
from mkt.constants.carriers import CARRIER_MAP
from mkt.constants.regions import REGIONS_DICT
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
        if request.method in permissions.SAFE_METHODS:
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

    def list(self, request, *args, **kwargs):
        data = self.req_data() or self.request.GET
        carrier, region = data['carrier'], data['region']
        carrier = (carrier if isinstance(carrier, (int, long)) else
                   CARRIER_MAP[carrier].id)
        region = (region if isinstance(region, (int, long)) else
                  REGIONS_DICT[region].id)
        self.queryset = self.queryset.filter(region=region, carrier=carrier)
        return super(LateCustomizationViewSet, self).list(request, *args,
                                                          **kwargs)

    def create(self, request, *args, **kwargs):
        data = self.req_data()
        try:
            self.require_operator_permission(
                request.user, data['carrier'], data['region'])
        except (KeyError, MultiValueDictKeyError):
            raise ParseError(
                "Operator permission required to add late-customization apps")
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
