from rest_framework import serializers

from mkt.webapps.serializers import (AppSerializer, ESAppFeedSerializer,
                                     ESAppFeedBrandSerializer, ESAppSerializer)


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
    @property
    def serializer_class(self):
        return ESAppSerializer

    def __init__(self, *args, **kwargs):
        self.many = kwargs.pop('many', False)
        self.limit = kwargs.pop('limit', None)
        super(AppESField, self).__init__(*args, **kwargs)

    def _attach_group(self, app):
        """Attach feed collection grouped apps (for 'mega collection')."""
        if self.context.get('group_apps'):
            group_index = self.context['group_apps'].get(unicode(app['id']))
            if group_index is None:
                # ES seems to sometimes return ID keyed on string and integer.
                group_index = self.context['group_apps'].get(app['id'])
            if group_index is not None:
                app.update(self.context['group_names'][group_index])
        return app

    def to_native(self, app_ids):
        """App ID to serialized app."""
        app_map = self.context['app_map']
        if self.context.get('group_apps'):
            # Attach groups.
            app_map = dict(self.context['app_map'])
            for app_id, app in app_map.items():
                app = self._attach_group(app)

        if self.many:
            if self.limit is not None:
                # If limit is specified, limit the number of apps.
                app_ids = app_ids[:self.limit]

            # Deserialize app ID to ES app data.
            partially_deserialized_apps = [
                app_map[app_id] for app_id in app_ids]

            # Deserialize ES app data to full data.
            apps = self.serializer_class(
                partially_deserialized_apps, many=True,
                context=self.context).data
            return apps
        else:
            # Single object, app_ids is only one app ID.
            app = self.serializer_class(app_map[app_ids],
                                        context=self.context).data
            return app

    def from_native(self, data):
        if self.many:
            return [app['id'] for app in data['apps']]
        else:
            return data['id']


class AppESHomeField(AppESField):
    """
    Like AppESField, except using ESAppFeedSerializer instead of
    ESAppSerializer. For a slimmer homepage.
    """
    @property
    def serializer_class(self):
        return ESAppFeedSerializer


class AppESHomeBrandField(AppESField):
    """
    Like AppESField, except using ESAppFeedSerializer instead of
    ESAppSerializer. For a slimmer homepage.
    """
    @property
    def serializer_class(self):
        return ESAppFeedBrandSerializer
