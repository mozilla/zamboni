import commonware.log
from rest_framework.permissions import BasePermission, SAFE_METHODS

from mkt.access import acl
from mkt.carriers import CARRIER_MAP as CARRIERS
from mkt.feed.models import FeedItem
from mkt.operators.models import OperatorPermission
from mkt.regions import REGIONS_DICT as REGIONS


log = commonware.log.getLogger('mkt.operators')


class OperatorAuthorization(BasePermission):
    """
    Permission class governing ability to interact with the operator
    dashboard.

    Rules:
    - All users may make safe requests.
    - Users with OperatorDashboard:* may make any request.
    - Users with an OperatorPermission object for the request's carrier and
      region may make any request.
    """
    def is_safe(self, request):
        return request.method in SAFE_METHODS

    def perm_exists(self, user, carrier, region):
        return OperatorPermission.objects.filter(
            user=user, carrier=carrier, region=region).exists()

    def is_admin(self, request):
        return acl.action_allowed(request, 'OperatorDashboard', '*')

    def has_permission(self, request, view):
        if self.is_safe(request):
            return True
        if request.user.is_anonymous():
            return False
        if self.is_admin(request):
            return True
        data = request.DATA if hasattr(request, 'DATA') else request.REQUEST
        carrier = data.get('carrier')
        region = data.get('region')
        if not carrier or not region:
            return False
        return self.perm_exists(request.user, CARRIERS[carrier].id,
                                REGIONS[region].id)


class OperatorShelfAuthorization(OperatorAuthorization):
    """
    Permission class governing ability to interact with operator shelves.

    Rules:
    - Inherits all rules from OperatorAuthorization.
    - Users with an OperatorPermission object for the object's carrier and
      region may make any request.
    - If the object is a FeedItem instance, the above check is performed on
      the corresponding FeedShelf instead.
    """
    def has_object_permission(self, request, view, obj):
        if self.is_safe(request):
            return True
        if request.user.is_anonymous():
            return False
        if self.is_admin(request):
            return True
        if isinstance(obj, FeedItem) and obj.shelf:
            obj = obj.shelf
        return self.perm_exists(request.user, region=obj.region,
                                carrier=obj.carrier)
