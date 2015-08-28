import hashlib
import json
from zipfile import BadZipfile, ZipFile

from django.core.exceptions import PermissionDenied
from django.db.transaction import non_atomic_requests
from django.forms import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404

import commonware
from rest_framework import exceptions
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.generics import ListAPIView
from rest_framework.mixins import (CreateModelMixin, ListModelMixin,
                                   RetrieveModelMixin)
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
                                 AllowReviewerReadOnly, AnyOf, ByHttpMethod,
                                 GroupPermission)
from mkt.api.paginator import ESPaginator
from mkt.constants.apps import MANIFEST_CONTENT_TYPE
from mkt.extensions.indexers import ExtensionIndexer
from mkt.extensions.models import Extension
from mkt.extensions.serializers import (ExtensionSerializer,
                                        ESExtensionSerializer)
from mkt.files.models import FileUpload
from mkt.search.filters import PublicContentFilter
from mkt.site.decorators import allow_cross_site_request, use_master
from mkt.site.utils import get_file_response
from mkt.submit.views import ValidationViewSet as SubmitValidationViewSet


log = commonware.log.getLogger('extensions.views')


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

        self.validate_upload(file_obj)  # Will raise exceptions if appropriate.
        user = request.user if request.user.is_authenticated() else None
        upload = FileUpload.from_post(
            file_obj, file_obj.name, file_obj.size, user=user)
        # FIXME: spawn validate task that does the real validation checks.
        # Right now we cheat and just set the upload as valid and processed
        # directly.
        upload.update(valid=True)
        serializer = self.get_serializer(upload)
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)

    def validate_upload(self, file_obj):
        # Do a basic check : is it a zipfile, and does it contain a manifest ?
        # Be careful to keep this as in-memory zip reading.
        if file_obj.content_type not in ('application/octet-stream',
                                         'application/zip'):
            raise exceptions.ParseError(
                _('The file sent has an unsupported content-type'))
        try:
            with ZipFile(file_obj, 'r') as z:
                manifest = z.read('manifest.json')
        except BadZipfile:
            raise exceptions.ParseError(
                _('The file sent is not a valid ZIP file.'))
        except KeyError:
            raise exceptions.ParseError(
                _("The archive does not contain a 'manifest.json' file."))
        try:
            json.loads(manifest)
        except ValueError:
            raise exceptions.ParseError(
                _("'manifest.json' in the archive is not a valid JSON file."))


class ExtensionViewSet(CORSMixin, SlugOrIdMixin, MarketplaceView,
                       CreateModelMixin, ListModelMixin, RetrieveModelMixin,
                       GenericViewSet):
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]
    cors_allowed_methods = ('get', 'patch', 'put', 'post', 'delete')
    permission_classes = [AnyOf(AllowAppOwner, AllowReviewerReadOnly,
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

    def create(self, request, *args, **kwargs):
        upload_pk = request.DATA.get('upload', '')
        if not upload_pk:
            raise exceptions.ParseError(_('No upload identifier specified.'))

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

        try:
            obj = Extension.from_upload(upload, user=request.user)
        except ValidationError as e:
            raise exceptions.ParseError(unicode(e))
        log.info('Extension created: %s' % obj.pk)
        serializer = self.get_serializer(obj)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


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

    @action()
    def publish(self, request, *args, **kwargs):
        obj = self.get_object()
        obj.publish()
        return Response(status=status.HTTP_202_ACCEPTED)

    @action()
    def reject(self, request, *args, **kwargs):
        # FIXME: we need to define what happens to rejected add-ons and how a
        # developer can re-submit them.
        obj = self.get_object()
        obj.reject()
        return Response(status=status.HTTP_202_ACCEPTED)


@allow_cross_site_request
def _download(request, extension, path, public=True):
    extension_etag = hashlib.sha256()
    extension_etag.update(unicode(extension.uuid))
    extension_etag.update(unicode(extension.file_version))
    return get_file_response(request, path,
                             content_type='application/zip',
                             etag=extension_etag.hexdigest(), public=public)


def download_signed(request, uuid, **kwargs):
    extension = get_object_or_404(Extension.objects.public(), uuid=uuid)

    log.info('Downloading add-on: %s from %s' % (
             extension.pk, extension.signed_file_path))
    return _download(request, extension, extension.signed_file_path)


def download_unsigned(request, uuid, **kwargs):
    extension = get_object_or_404(Extension, uuid=uuid)

    def is_author():
        return extension.authors.filter(pk=request.user.pk).exists()

    def is_reviewer():
        return action_allowed(request, 'Extensions', 'Review')

    if request.user.is_authenticated() and (is_author() or is_reviewer()):
        log.info('Downloading unsigned add-on: %s from %s' % (
                 extension.pk, extension.file_path))
        return _download(request, extension, extension.file_path, public=False)
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
