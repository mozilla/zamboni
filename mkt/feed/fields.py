from rest_framework import serializers

from mkt.webapps.serializers import AppSerializer


class FeedCollectionMembershipField(serializers.RelatedField):
    """
    Serializer field to be used with M2M model fields to Webapps, replacing
    instances of the Membership instances with serializations of the Webapps
    that they correspond to.
    """
    def to_native(self, qs, use_es=False):
        return AppSerializer(qs, context=self.context).data
