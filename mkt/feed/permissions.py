import commonware.log
from rest_framework.permissions import BasePermission, SAFE_METHODS

from mkt.access import acl


log = commonware.log.getLogger('mkt.feed')


class FeedPermission(BasePermission):
    """
    Permission class governing ability to interact with Feed-related
    APIs.

    Rules:
    - All users may make GET, HEAD, OPTIONS requests.
    - Users with Feed:Curate may make any request.
    """
    def is_safe(self, request):
        return request.method in SAFE_METHODS

    def has_curate_permission(self, request):
        return acl.action_allowed(request, 'Feed', 'Curate')

    def has_permission(self, request, view):
        if self.is_safe(request):
            return True
        return self.has_curate_permission(request)
