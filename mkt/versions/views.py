from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, ParseError

import mkt
from mkt.api.authentication import (RestAnonymousAuthentication,
                                    RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.base import CORSMixin
from mkt.api.permissions import (AllowReadOnlyIfPublic, AllowRelatedAppOwner,
                                 AnyOf, GroupPermission)
from mkt.constants import APP_FEATURES
from mkt.versions.models import Version
from mkt.versions.serializers import FileStatusSerializer, VersionSerializer


class VersionStatusViewSet(mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Special API view used by senior reviewers and admins to modify a version
    (actually the corresponding File) status."""
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]
    permission_classes = [GroupPermission('Admin', '%')]
    serializer_class = FileStatusSerializer
    cors_allowed_methods = ['patch']

    def get_object(self):
        # Since we are fetching a totally different object than the pk the
        # client is passing, we need to make sure to override the pk in
        # self.kwargs, DRF uses it as a precautionary measure in in pre_save().
        obj = self.kwargs['version'].all_files[0]
        self.kwargs[self.lookup_field] = obj.pk
        return obj

    def update(self, request, *args, **kwargs):
        # PUT is disallowed, only PATCH is accepted for this endpoint.
        if request.method == 'PUT':
            raise MethodNotAllowed('PUT')
        res = super(VersionStatusViewSet, self).update(
            request, *args, **kwargs)
        app = self.object.version.webapp
        res.data['app_status'] = mkt.STATUS_CHOICES_API[app.status]
        return res


class VersionViewSet(CORSMixin, mixins.RetrieveModelMixin,
                     mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = Version.objects.exclude(webapp__status=mkt.STATUS_DELETED)
    serializer_class = VersionSerializer
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]
    permission_classes = [AnyOf(AllowReadOnlyIfPublic,
                                AllowRelatedAppOwner,
                                GroupPermission('Apps', 'Review'),
                                GroupPermission('Admin', '%'))]
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

    @action(methods=['PATCH'],
            cors_allowed_methods=VersionStatusViewSet.cors_allowed_methods)
    def status(self, request, *args, **kwargs):
        self.queryset = Version.with_deleted.all()
        kwargs['version'] = self.get_object()
        view = VersionStatusViewSet.as_view({'patch': 'update'})
        return view(request, *args, **kwargs)
