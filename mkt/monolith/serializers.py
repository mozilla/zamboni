import json
from rest_framework import serializers

from .models import MonolithRecord


class MonolithSerializer(serializers.ModelSerializer):
    class Meta:
        model = MonolithRecord
        fields = ('key', 'recorded', 'user_hash', 'value')

    def transform_value(self, obj, value):
        if not isinstance(value, basestring):
            return value
        return json.loads(value)
