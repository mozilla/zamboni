from rest_framework.permissions import BasePermission, SAFE_METHODS

from mkt.access import acl


class AllowExtensionReviewerReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS and acl.action_allowed(
            request, 'ContentTools', 'AddonReview')

    def has_object_permission(self, request, view, obj):
        # The object does not matter: as long as it's for a read-only action,
        # the reviewer will have access.
        return self.has_permission(request, view)


class AllowOwnerButReadOnlyIfBlocked(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated()

    def has_object_permission(self, request, view, obj):
        if not obj.authors.filter(pk=request.user.pk).exists():
            return False

        if not obj.is_blocked():
            # If the extension is not blocked, being an author is good enough.
            return True
        else:
            # If the extension *is* blocked, authors are only allowed for
            # read-only actions.
            return request.method in SAFE_METHODS
