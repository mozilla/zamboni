from rest_framework import serializers

from mkt.api.fields import ESTranslationSerializerField
from mkt.webapps.serializers import AppSerializer, ESAppSerializer


class FeedCollectionMembershipField(serializers.RelatedField):
    """
    Serializer field to be used with M2M model fields to Webapps, replacing
    instances of the Membership instances with serializations of the Webapps
    that they correspond to.
    """
    def to_native(self, qs, use_es=False):
        return AppSerializer(qs, context=self.context).data


class AppESField(serializers.Field):
    """
    Deserialize an app id using ESAppSerializer.

    For object-to-app relations in ES, we store app IDs as a property of the
    object. Since we want to limit ES queries, we batch-query for objects,
    and then batch-query for apps. Afterwards, we set up app_map which is
    used to deserialize app IDs to app ES data. This class helps deserialize
    using that map and expects app IDs (i.e., passed through source).

    self.context['app_map'] -- mapping from app ID to app ES object
    """
    def __init__(self, *args, **kwargs):
        self.many = kwargs.pop('many', False)
        super(AppESField, self).__init__(*args, **kwargs)

    def to_native(self, app_ids):
        """App ID to serialized app."""
        if self.many:
            # Deserialize app ID to ES app data.
            partially_deserialized_apps = [
                self.context['app_map'][app_id] for app_id in app_ids]
            # Deserialize ES app data to full data.
            apps = ESAppSerializer(
                partially_deserialized_apps, many=True,
                context=self.context).data
            return apps
        else:
            # Single object, app_ids is only one app ID.
            app = ESAppSerializer(self.context['app_map'][app_ids],
                                  context=self.context).data
            return app

    def from_native(self, data):
        if self.many:
            return [app['id'] for app in data['apps']]
        else:
            return data['id']
