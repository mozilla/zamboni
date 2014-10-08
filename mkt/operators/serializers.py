from rest_framework import serializers

import mkt
from mkt.api.fields import SlugChoiceField

from .models import OperatorPermission


class OperatorPermissionSerializer(serializers.ModelSerializer):
    carrier = SlugChoiceField(choices_dict=mkt.carriers.CARRIER_MAP)
    region = SlugChoiceField(choices_dict=mkt.regions.REGION_LOOKUP)

    class Meta:
        fields = ('carrier', 'region')
        model = OperatorPermission
