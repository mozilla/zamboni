import hashlib

from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.db.transaction import non_atomic_requests
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404

import commonware
from rest_framework import exceptions
from rest_framework import status
from rest_framework.decorators import detail_route
from rest_framework.generics import ListAPIView
from rest_framework.mixins import (DestroyModelMixin, ListModelMixin,
                                   RetrieveModelMixin, UpdateModelMixin)
from rest_framework.parsers import FileUploadParser
from rest_framework.permissions import AllowAny, SAFE_METHODS
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
from mkt.extensions.forms import ExtensionSearchForm
from mkt.extensions.indexers import ExtensionIndexer
from mkt.extensions.models import Extension, ExtensionVersion
from mkt.extensions.permissions import AllowExtensionReviewerReadOnly
from mkt.extensions.serializers import (ESExtensionSerializer,
                                        ExtensionSerializer,
                                        ExtensionVersionSerializer)
from mkt.extensions.validation import ExtensionValidator
from mkt.files.models import FileUpload
from mkt.search.filters import (ExtensionSearchFormFilter, PublicContentFilter,
                                SearchQueryFilter, SortingFilter)
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

        # self.model.from_upload() will raise ParseError if appropriate.
        obj = self.model.from_upload(upload, **params)
        log.info('%s created: %s' % (self.model, self.model.pk))

        # TODO: change create_comm_note to just take a version.
        if 'extension_pk' in self.kwargs:
            create_comm_note(obj.extension, obj, request.user,
                             request.DATA.get('message', ''),
                             note_type=comm.SUBMISSION)
        else:
            create_comm_note(obj, obj.latest_version, request.user,
                             request.DATA.get('message', ''),
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

        # Will raise ParseError exceptions if appropriate.
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
                       DestroyModelMixin, ListModelMixin, RetrieveModelMixin,
                       SlugOrIdMixin, UpdateModelMixin, GenericViewSet):
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]
    cors_allowed_methods = ('get', 'patch', 'put', 'post', 'delete')
    model = Extension
    permission_classes = [AnyOf(AllowAppOwner, AllowExtensionReviewerReadOnly,
                                AllowReadOnlyIfPublic)]
    queryset = Extension.objects.without_deleted()
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

    def update(self, request, *args, **kwargs):
        partial = kwargs.get('partial', False)
        if not partial:
            # PUT are not supported, only PATCH is.
            raise exceptions.MethodNotAllowed(request.method)
        return super(ExtensionViewSet, self).update(request, *args, **kwargs)


class ExtensionSearchView(CORSMixin, MarketplaceView, ListAPIView):
    """
    Base extension search view returning only public content (and not allowing
    any search query at the moment).
    """
    cors_allowed_methods = ['get']
    authentication_classes = [RestSharedSecretAuthentication,
                              RestOAuthAuthentication]
    permission_classes = [AllowAny]
    filter_backends = [ExtensionSearchFormFilter, PublicContentFilter,
                       SearchQueryFilter, SortingFilter]
    serializer_class = ESExtensionSerializer
    paginator_class = ESPaginator
    form_class = ExtensionSearchForm

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
    queryset = Extension.objects.without_deleted().pending()
    serializer_class = ExtensionSerializer


class ExtensionVersionViewSet(CORSMixin, MarketplaceView, CreateExtensionMixin,
                              DestroyModelMixin, ListModelMixin,
                              RetrieveModelMixin, GenericViewSet):
    authentication_classes = ExtensionViewSet.authentication_classes
    cors_allowed_methods = ('get', 'patch', 'put', 'post', 'delete')
    model = ExtensionVersion
    # Note: In this viewset, permissions are checked against the parent
    # extension.
    permission_classes = ExtensionViewSet.permission_classes
    queryset = ExtensionVersion.objects.without_deleted()
    serializer_class = ExtensionVersionSerializer

    def check_permissions(self, request):
        """Check permissions as normal, but also check that we can access the
        parent extension."""
        super(ExtensionVersionViewSet, self).check_permissions(request)

        extension = self.get_extension_object()
        # You can't modify or create versions on disabled extensions, even if
        # you are the owner.
        if extension.disabled and self.request.method not in SAFE_METHODS:
            raise PermissionDenied(
                _(u'Modifying or submitting versions is forbidden for disabled'
                  u' Add-ons.'))
        # Check object permissions (the original implementation, since we
        # provide a different one) on the parent extension.
        super(ExtensionVersionViewSet, self).check_object_permissions(
            request, extension)

    def check_object_permissions(self, request, obj):
        """Check object permissions against the extension, not the version."""
        super(ExtensionVersionViewSet, self).check_object_permissions(
            request, obj.extension)

    def get_extension_object(self):
        """Return the parent Extension object using the GET parameter passed
        to the view."""
        if hasattr(self, 'extension_object'):
            return self.extension_object
        identifier = self.kwargs.get('extension_pk')
        if not identifier:
            raise ImproperlyConfigured(
                'extension_pk should be passed to ExtensionVersionViewSet.')
        try:
            self.extension_object = (
                Extension.objects.without_deleted().by_identifier(identifier))
        except Extension.DoesNotExist:
            raise Http404
        return self.extension_object

    def get_queryset(self):
        """Return the ExtensionVersion queryset, filtered to only consider the
        children of the parent Extension."""
        qs = super(ExtensionVersionViewSet, self).get_queryset()
        return qs.filter(extension=self.get_extension_object())

    @detail_route(
        methods=['post'],
        cors_allowed_methods=['post'],
        permission_classes=ReviewersExtensionViewSet.permission_classes)
    def publish(self, request, *args, **kwargs):
        obj = self.get_object()
        obj.publish()
        create_comm_note(obj.extension, obj, request.user,
                         request.DATA.get('message', ''),
                         note_type=comm.APPROVAL)
        return Response(status=status.HTTP_202_ACCEPTED)

    @detail_route(
        methods=['post'],
        cors_allowed_methods=['post'],
        permission_classes=ReviewersExtensionViewSet.permission_classes)
    def reject(self, request, *args, **kwargs):
        obj = self.get_object()
        obj.reject()
        create_comm_note(obj.extension, obj, request.user,
                         request.DATA.get('message', ''),
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
    """Download the signed archive for a given public extension/version."""
    extension = get_object_or_404(
        Extension.objects.without_deleted().public(), uuid=uuid)
    version = get_object_or_404(
        extension.versions.without_deleted().public(), pk=kwargs['version_id'])

    log.info('Downloading public add-on: %s version %s from %s' % (
             extension.pk, version.pk, version.signed_file_path))
    return _download(request, extension, version, version.signed_file_path)


def download_signed_reviewer(request, uuid, **kwargs):
    """Download an archive for a given extension/version, signed on-the-fly
    with reviewers certificate.

    Only reviewers can access this."""
    extension = get_object_or_404(
        Extension.objects.without_deleted(), uuid=uuid)
    version = get_object_or_404(
        extension.versions.without_deleted(), pk=kwargs['version_id'])

    def is_reviewer():
        return action_allowed(request, 'Extensions', 'Review')

    if request.user.is_authenticated() and is_reviewer():
        version.reviewer_sign_if_necessary()
        log.info(
            'Downloading reviewers signed add-on: %s version %s from %s' % (
                extension.pk, version.pk, version.reviewer_signed_file_path))
        return _download(request, extension, version,
                         version.reviewer_signed_file_path, public=False)
    else:
        raise PermissionDenied


def download_unsigned(request, uuid, **kwargs):
    """Download the unsigned archive for a given extension/version.

    Only reviewers and developers can do this."""
    extension = get_object_or_404(
        Extension.objects.without_deleted(), uuid=uuid)
    version = get_object_or_404(
        extension.versions.without_deleted(), pk=kwargs['version_id'])

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
    extension = get_object_or_404(
        Extension.objects.without_deleted(), uuid=uuid)

    if extension.is_public():
        # Let ETag/Last-Modified be handled by the generic middleware for now.
        # If that turns out to be a problem, we'll set them manually.
        return JsonResponse(extension.mini_manifest,
                            content_type=MANIFEST_CONTENT_TYPE)
    else:
        raise Http404


@allow_cross_site_request
def mini_manifest_reviewer(request, uuid, **kwargs):
    extension = get_object_or_404(
        Extension.objects.without_deleted(), uuid=uuid)
    version = get_object_or_404(
        extension.versions.without_deleted(), pk=kwargs['version_id'])

    def is_reviewer():
        return action_allowed(request, 'Extensions', 'Review')

    if request.user.is_authenticated() and is_reviewer():
        manifest = version.reviewer_mini_manifest
        # Let ETag/Last-Modified be handled by the generic middleware for now.
        # If that turns out to be a problem, we'll set them manually.
        return JsonResponse(manifest, content_type=MANIFEST_CONTENT_TYPE)
    else:
        raise PermissionDenied
