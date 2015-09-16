import hashlib

from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.db.transaction import non_atomic_requests
from django.forms import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404

import commonware
from rest_framework import exceptions
from rest_framework import status
from rest_framework.decorators import detail_route
from rest_framework.generics import ListAPIView
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from rest_framework.parsers import FileUploadParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from tower import ugettext as _

from mkt.access.acl import action_allowed
from mkt.api.authentication import (RestAnonymousAuthentication,
                                    RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.base import CORSMixin, MarketplaceView, SlugOrIdMixin
from mkt.api.permissions import (AllowAppOwner, AllowReadOnlyIfPublic,
                                 AnyOf, ByHttpMethod, GroupPermission)
from mkt.api.paginator import ESPaginator
from mkt.comm.utils import create_comm_note
from mkt.constants import comm
from mkt.constants.apps import MANIFEST_CONTENT_TYPE
from mkt.extensions.indexers import ExtensionIndexer
from mkt.extensions.models import Extension, ExtensionVersion
from mkt.extensions.permissions import AllowExtensionReviewerReadOnly
from mkt.extensions.serializers import (ESExtensionSerializer,
                                        ExtensionSerializer,
                                        ExtensionVersionSerializer)
from mkt.extensions.validation import ExtensionValidator
from mkt.files.models import FileUpload
from mkt.search.filters import PublicContentFilter
from mkt.site.decorators import allow_cross_site_request, use_master
from mkt.site.utils import get_file_response
from mkt.submit.views import ValidationViewSet as SubmitValidationViewSet


log = commonware.log.getLogger('extensions.views')


class CreateExtensionMixin(object):
    def create(self, request, *args, **kwargs):
        upload_pk = request.DATA.get('validation_id', '')
        if not upload_pk:
            raise exceptions.ParseError(_('No validation_id specified.'))

        if not request.user.is_authenticated():
            raise exceptions.PermissionDenied(
                _('You need to be authenticated to perform this action.'))

        try:
            upload = FileUpload.objects.get(pk=upload_pk, user=request.user)
        except FileUpload.DoesNotExist:
            raise Http404(_('No such upload.'))
        if not upload.valid:
            raise exceptions.ParseError(
                _('The specified upload has not passed validation.'))

        if 'extension_pk' in self.kwargs:
            # We are creating a new ExtensionVersion.
            params = {'parent': self.get_extension_object()}
        else:
            # We are creating a new Extension
            params = {'user': request.user}
        try:
            obj = self.model.from_upload(upload, **params)
        except ValidationError as e:
            raise exceptions.ParseError(unicode(e))

        log.info('%s created: %s' % (self.model, self.model.pk))

        # TODO: change create_comm_note to just take a version.
        if 'extension_pk' in self.kwargs:
            create_comm_note(obj.extension, obj, request.user, '',
                             note_type=comm.SUBMISSION)
        else:
            create_comm_note(obj, obj.latest_version, request.user, '',
                             note_type=comm.SUBMISSION)

        serializer = self.get_serializer(obj)

        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ValidationViewSet(SubmitValidationViewSet):
    # Typical usage:
    # cat /tmp/extension.zip | curling -X POST --data-binary '@-' \
    # http://localhost:8000/api/v2/extensions/validation/
    cors_allowed_headers = ('Content-Disposition', 'Content-Type')
    parser_classes = (FileUploadParser,)

    @use_master
    def create(self, request, *args, **kwargs):
        file_obj = request.FILES.get('file', None)
        if not file_obj:
            raise exceptions.ParseError(_('Missing file in request.'))

        # Will raise exceptions if appropriate.
        ExtensionValidator(file_obj).validate()

        user = request.user if request.user.is_authenticated() else None
        upload = FileUpload.from_post(
            file_obj, file_obj.name, file_obj.size, user=user)
        # FIXME: spawn validate task that does the real validation checks.
        # Right now we cheat and just set the upload as valid and processed
        # directly.
        upload.update(valid=True)
        serializer = self.get_serializer(upload)
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)


class ExtensionViewSet(CORSMixin, MarketplaceView, CreateExtensionMixin,
                       SlugOrIdMixin, ListModelMixin, RetrieveModelMixin,
                       GenericViewSet):
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]
    cors_allowed_methods = ('get', 'patch', 'put', 'post', 'delete')
    model = Extension
    permission_classes = [AnyOf(AllowAppOwner, AllowExtensionReviewerReadOnly,
                                AllowReadOnlyIfPublic)]
    queryset = Extension.objects.all()
    serializer_class = ExtensionSerializer

    def filter_queryset(self, qs):
        if self.action == 'list':
            # The listing API only allows you to see extensions you've
            # developed.
            if not self.request.user.is_authenticated():
                raise exceptions.PermissionDenied(
                    'Anonymous listing not allowed.')
            qs = qs.filter(authors=self.request.user)
        return qs


class ExtensionSearchView(CORSMixin, MarketplaceView, ListAPIView):
    """
    Base extension search view returning only public content (and not allowing
    any search query at the moment).
    """
    cors_allowed_methods = ['get']
    authentication_classes = [RestSharedSecretAuthentication,
                              RestOAuthAuthentication]
    permission_classes = [AllowAny]
    filter_backends = [PublicContentFilter]  # No search query for now.
    serializer_class = ESExtensionSerializer
    paginator_class = ESPaginator

    def get_queryset(self):
        return ExtensionIndexer.search()

    @classmethod
    def as_view(cls, **kwargs):
        # Make all search views non_atomic: they should not need the db, or
        # at least they should not need to make db writes, so they don't need
        # to be wrapped in transactions.
        view = super(ExtensionSearchView, cls).as_view(**kwargs)
        return non_atomic_requests(view)


class ReviewersExtensionViewSet(CORSMixin, SlugOrIdMixin, MarketplaceView,
                                ListModelMixin, RetrieveModelMixin,
                                GenericViewSet):
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]
    cors_allowed_methods = ('get', 'post')
    permission_classes = (ByHttpMethod({
        'options': AllowAny,
        'post': GroupPermission('Extensions', 'Review'),
        'get': GroupPermission('Extensions', 'Review'),
    }),)
    queryset = Extension.objects.pending()
    serializer_class = ExtensionSerializer


class ExtensionVersionViewSet(CORSMixin, MarketplaceView, CreateExtensionMixin,
                              ListModelMixin, RetrieveModelMixin,
                              GenericViewSet):
    authentication_classes = ExtensionViewSet.authentication_classes
    cors_allowed_methods = ('get', 'patch', 'put', 'post', 'delete')
    model = ExtensionVersion
    # Note: In this viewset, permissions are checked against the parent
    # extension.
    permission_classes = ExtensionViewSet.permission_classes
    queryset = ExtensionVersion.objects.all()
    serializer_class = ExtensionVersionSerializer

    def check_permissions(self, request):
        """Check permissions as normal, but also check that we can access the
        parent extension."""
        super(ExtensionVersionViewSet, self).check_permissions(request)

        extension = self.get_extension_object()
        super(ExtensionVersionViewSet, self).check_object_permissions(
            request, extension)

    def check_object_permissions(self, request, obj):
        """Check object permissions against the extension, not the version."""
        super(ExtensionVersionViewSet, self).check_object_permissions(
            request, obj.extension)

    def filter_extension_queryset(self, qs, filter_prefix=''):
        """Filter queryset passed in argument to find the parent Extension
        by slug or pk."""
        extension_pk = self.kwargs.get('extension_pk')
        if not extension_pk:
            raise ImproperlyConfigured(
                'extension_pk should be passed to ExtensionVersionViewSet.')
        if extension_pk.isdigit():
            filters = {'%spk' % filter_prefix: extension_pk}
        else:
            filters = {'%sslug' % filter_prefix: extension_pk}
        return qs.filter(**filters)

    def get_extension_object(self):
        """Return the parent Extension object directly."""
        try:
            extension = self.filter_extension_queryset(
                ExtensionViewSet.queryset).get()
        except Extension.DoesNotExist:
            raise Http404
        return extension

    def get_queryset(self):
        """Return the ExtensionVersion queryset, filtered to only consider the
        children of the parent Extension."""
        qs = super(ExtensionVersionViewSet, self).get_queryset()
        return self.filter_extension_queryset(qs, filter_prefix='extension__')

    @detail_route(
        methods=['post'],
        cors_allowed_methods=['post'],
        permission_classes=ReviewersExtensionViewSet.permission_classes)
    def publish(self, request, *args, **kwargs):
        obj = self.get_object()
        obj.publish()
        create_comm_note(obj.extension, obj, request.user, '',
                         note_type=comm.APPROVAL)
        return Response(status=status.HTTP_202_ACCEPTED)

    @detail_route(
        methods=['post'],
        cors_allowed_methods=['post'],
        permission_classes=ReviewersExtensionViewSet.permission_classes)
    def reject(self, request, *args, **kwargs):
        obj = self.get_object()
        obj.reject()
        create_comm_note(obj.extension, obj, request.user, '',
                         note_type=comm.REJECTION)
        return Response(status=status.HTTP_202_ACCEPTED)


@allow_cross_site_request
def _download(request, extension, version, path, public=True):
    extension_etag = hashlib.sha256()
    extension_etag.update(unicode(extension.uuid))
    extension_etag.update(unicode(version.pk))
    return get_file_response(request, path,
                             content_type='application/zip',
                             etag=extension_etag.hexdigest(), public=public)


def download_signed(request, uuid, **kwargs):
    extension = get_object_or_404(Extension.objects.public(), uuid=uuid)
    version = extension.versions.get(pk=kwargs['version_id'])

    log.info('Downloading add-on: %s version %s from %s' % (
             extension.pk, version.pk, version.signed_file_path))
    return _download(request, extension, version, version.signed_file_path)


def download_unsigned(request, uuid, **kwargs):
    extension = get_object_or_404(Extension, uuid=uuid)
    version = extension.versions.get(pk=kwargs['version_id'])

    def is_author():
        return extension.authors.filter(pk=request.user.pk).exists()

    def is_reviewer():
        return action_allowed(request, 'Extensions', 'Review')

    if request.user.is_authenticated() and (is_author() or is_reviewer()):
        log.info('Downloading unsigned add-on: %s version %s from %s' % (
                 extension.pk, version.pk, version.file_path))
        return _download(request, extension, version, version.file_path,
                         public=False)
    else:
        raise PermissionDenied


@allow_cross_site_request
def mini_manifest(request, uuid, **kwargs):
    extension = get_object_or_404(Extension, uuid=uuid)

    if extension.is_public():
        # Let ETag/Last-Modified be handled by the generic middleware for now.
        # If that turns out to be a problem, we'll set them manually.
        return JsonResponse(extension.mini_manifest,
                            content_type=MANIFEST_CONTENT_TYPE)
    else:
        raise Http404
