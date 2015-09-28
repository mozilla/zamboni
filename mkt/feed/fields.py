from rest_framework import serializers

from mkt.fireplace.serializers import FeedFireplaceESAppSerializer
from mkt.webapps.serializers import (AppSerializer, ESAppFeedSerializer,
                                     ESAppFeedCollectionSerializer,
                                     ESAppSerializer)


class FeedCollectionMembershipField(serializers.PrimaryKeyRelatedField):
    """
    Serializer field to be used with M2M model fields to Webapps, replacing
    instances of the Membership instances with serializations of the Webapps
    that they correspond to.
    """

    def to_representation(self, qs, use_es=False):
        return AppSerializer(qs, context=self.context).data


class AppESField(serializers.Field):
    """
    Deserialize an app id using ESAppSerializer.

    For object-to-app relations in ES, we store app IDs as a property of the
    object. Since we want to limit ES queries, we batch-query for objects,
    and then batch-query for apps. Afterwards, we set up app_map which is
    used to deserialize app IDs to app ES data. This class helps deserialize
    using that map and expects app IDs (i.e., passed through source).

    If the app does not exist in the app map, we consider that the app was
    filtered out (as a result of status, region, device filtering). In that
    case, we just return None or exclude it.

    self.context['app_map'] -- mapping from app ID to app ES object
    """
    app_serializer_classes = {
        'fireplace': FeedFireplaceESAppSerializer,
    }

    @property
    def serializer_class(self):
        request = self.context['request']
        app_serializer = request.GET.get('app_serializer')

        # TODO: remove once fireplace is using
        # /consumer/feed/...?app_serializer=fireplace.
        if app_serializer is None and '/fireplace/' in request.path:
            app_serializer = 'fireplace'

        return self.app_serializer_classes.get(app_serializer, ESAppSerializer)

    def __init__(self, *args, **kwargs):
        self.many = kwargs.pop('many', False)
        self.limit = kwargs.pop('limit', None)
        super(AppESField, self).__init__(*args, **kwargs)

    def _attach_group(self, app):
        """
        Attach feed collection grouped apps (for 'mega collection').
        Sets app.group_translations to something like
            [{'lang': 'en-US', 'string': 'My Group'}].
        """
        if self.context.get('group_apps'):
            group_index = self.context['group_apps'].get(unicode(app['id']))
            if group_index is None:
                # ES seems to sometimes return ID keyed on string and integer.
                group_index = self.context['group_apps'].get(app['id'])
            if group_index is not None:
                if isinstance(app, dict):
                    app.update(self.context['group_names'][group_index])
                else:
                    setattr(app, 'group_translations',
                            self.context['group_names'][group_index]
                                        ['group_translations'])
        return app

    def to_representation(self, app_ids):
        """App ID to serialized app."""
        app_map = self.context['app_map']
        if self.context.get('group_apps'):
            # Attach groups.
            app_map = dict(self.context['app_map'])
            for app_id, app in app_map.items():
                app = self._attach_group(app)

        if self.many:
            # Deserialize app ID to ES app data.
            partially_deserialized_apps = [
                app_map[app_id] for app_id in app_ids if app_map.get(app_id)]

            # Deserialize ES app data to full data.
            apps = self.serializer_class(
                partially_deserialized_apps, many=True,
                context=self.context).data

            # If limit is specified, limit the number of apps.
            if self.limit is not None:
                apps = apps[:self.limit]

            return apps
        else:
            # Single object, app_ids is only one app ID.
            if not app_map.get(app_ids):
                return None

            return self.serializer_class(app_map[app_ids],
                                         context=self.context).data

    def to_internal_value(self, data):
        if self.many:
            return [app['id'] for app in data['apps']]
        else:
            return data['id']


class AppESHomeField(AppESField):
    """
    Like AppESField, except using ESAppFeedSerializer instead of
    ESAppSerializer. For a slimmer homepage since apps/brands only need
    enough to render the market tile.
    """
    @property
    def serializer_class(self):
        return ESAppFeedSerializer


class AppESHomePromoCollectionField(AppESField):
    """
    Like AppESField, except using ESAppFeedCollectionSerializer instead of
    ESAppSerializer. For a slimmer homepage since collection/shelves only
    need icons.
    """
    @property
    def serializer_class(self):
        return ESAppFeedCollectionSerializer
