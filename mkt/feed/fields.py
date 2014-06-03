from rest_framework import serializers

from mkt.webapps.serializers import AppSerializer


class FeedCollectionMembershipField(serializers.RelatedField):
    def to_native(self, qs, use_es=False):
        return AppSerializer(qs, context=self.context).data
