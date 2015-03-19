from django.db import models

import mkt
from mkt.site.models import ModelBase


class OperatorPermission(ModelBase):
    """
    Model representing an object-level permission of a user to a
    carrier/region pair.

    The presence of an OperatorPermission object with a user, carrier, and
    region implies that user has permission to perform admin operations for
    that carrier in that region.
    """
    carrier = models.PositiveIntegerField(choices=mkt.carriers.CARRIER_CHOICES)
    region = models.PositiveIntegerField(
        choices=mkt.regions.REGIONS_CHOICES_ID)
    user = models.ForeignKey('users.UserProfile')

    class Meta:
        db_table = 'operator_permission'
        unique_together = ('user', 'carrier', 'region')

    @classmethod
    def has_permission(cls, user, carrier, region):
        """
        Returns a boolean indicating whether an OperatorPermission object
        exists for the passed user, carrier, and region.

        Example:
        has_permission = OperatorPermission.has_permission(
            request.user, request.REGION.id, get_carrier_id())
        """
        return cls.objects.get(
            user=user, carrier=carrier, region=region).exists()

    @classmethod
    def user_is_operator(cls, user):
        """
        Returns a boolean indicating whether the passed user has operator
        permissions for any carrier/region pair.

        Example:
        is_operator = OperatorPermission.user_is_operator(request.user)
        """
        return (user.is_authenticated() and
                cls.objects.filter(user=user).exists())
