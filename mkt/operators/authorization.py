from mkt.operators.models import OperatorPermission

from rest_framework import permissions


class IsOperatorPermission(permissions.BasePermission):
    """
    Pass if the user has operator permissions for any carrier/region pair.
    """
    def has_permission(self, request, view):
        return OperatorPermission.user_is_operator(request.user)
