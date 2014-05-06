from rest_framework import mixins, viewsets
from rest_framework.exceptions import ParseError

import amo
from mkt.api.authorization import (AllowReadOnlyIfPublic, AllowRelatedAppOwner,
                                   AnyOf, GroupPermission)
from mkt.api.base import CORSMixin
from mkt.constants import APP_FEATURES
from mkt.versions.serializers import VersionSerializer
from versions.models import Version


class VersionViewSet(CORSMixin, mixins.RetrieveModelMixin,
                     mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = Version.objects.filter(
        addon__type=amo.ADDON_WEBAPP).exclude(addon__status=amo.STATUS_DELETED)
    serializer_class = VersionSerializer
    authorization_classes = []
    permission_classes = [AnyOf(AllowRelatedAppOwner,
                                GroupPermission('Apps', 'Review'),
                                AllowReadOnlyIfPublic)]
    cors_allowed_methods = ['get', 'patch', 'put']

    def update(self, request, *args, **kwargs):
        """
        Allow a version's features to be updated.
        """
        obj = self.get_object()

        # Update features if they are provided.
        if 'features' in request.DATA:

            # Raise an exception if any invalid features are passed.
            invalid = [f for f in request.DATA['features'] if f.upper() not in
                       APP_FEATURES.keys()]
            if any(invalid):
                raise ParseError('Invalid feature(s): %s' % ', '.join(invalid))

            # Update the value of each feature (note: a feature not present in
            # the form data is assumed to be False)
            data = {}
            for key, name in APP_FEATURES.items():
                field_name = 'has_' + key.lower()
                data[field_name] = key.lower() in request.DATA['features']
            obj.features.update(**data)

            del request.DATA['features']

        return super(VersionViewSet, self).update(request, *args, **kwargs)
