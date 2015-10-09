from rest_framework.permissions import BasePermission, SAFE_METHODS

from mkt.access import acl


class AllowExtensionReviewerReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS and acl.action_allowed(
            request, 'ContentTools', 'AddonReview')

    def has_object_permission(self, request, view, object):
        # The object does not matter: as long as it's for a read-only action,
        # the reviewer will have access.
        return self.has_permission(request, view)
