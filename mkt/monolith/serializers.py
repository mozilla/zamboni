import json
from rest_framework import serializers

from .models import MonolithRecord


class MonolithSerializer(serializers.ModelSerializer):
    value = serializers.JSONField()

    class Meta:
        model = MonolithRecord
        fields = ('key', 'recorded', 'user_hash', 'value')

    def to_representation(self, data):
        data = super(MonolithSerializer, self).to_representation(data)
        if isinstance(data['value'], basestring):
            data['value'] = json.loads(data['value'])
        return data
