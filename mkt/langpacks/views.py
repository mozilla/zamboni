# -*- coding: utf-8 -*-
import hashlib
from uuid import UUID

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import condition

import commonware
from rest_framework import viewsets

from mkt.access.acl import action_allowed
from mkt.api.authentication import (RestAnonymousAuthentication,
                                    RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.authorization import (AllowReadOnlyIfPublic, AnyOf,
                                   GroupPermission)
from mkt.api.base import CORSMixin, MarketplaceView
from mkt.constants import MANIFEST_CONTENT_TYPE
from mkt.langpacks.models import LangPack
from mkt.langpacks.serializers import (LangPackSerializer,
                                       LangPackUploadSerializer)
from mkt.site.decorators import allow_cross_site_request
from mkt.site.utils import HttpResponseSendFile


log = commonware.log.getLogger('z.api')


class LangPackViewSet(CORSMixin, MarketplaceView, viewsets.ModelViewSet):
    model = LangPack
    cors_allowed_methods = ('get', 'post', 'put', 'patch', 'delete')
    permission_classes = [AnyOf(AllowReadOnlyIfPublic,
                                GroupPermission('LangPacks', '%'))]
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]
    serializer_class = LangPackSerializer

    def filter_queryset(self, qs):
        """Filter GET requests with active=True, unless we have the permissions
        to do differently."""
        if self.request.method == 'GET':
            active_parameter = self.request.GET.get('active')
            fxos_version_parameter = self.request.GET.get('fxos_version')

            if 'pk' in self.kwargs:
                # No filtering at all if we're trying to see a detail page: the
                # permission_classes mechanism will handle the rest for us. It
                # reveals the existence of the langpack but that's OK.
                return qs

            # Handle 'active' filtering.
            if active_parameter in ('null', 'false'):
                if action_allowed(self.request, 'LangPacks', '%'):
                    # If active=null, we don't need to filter at all (we show
                    # all langpacks regardless of their 'active' flag value).
                    # If it's false, we only show inactive langpacks.
                    if active_parameter == 'false':
                        qs = qs.filter(active=False)
                else:
                    # We don't have the permission, but the parameter to filter
                    # was passed, return a permission denied, someone is trying
                    # to see things he shouldn't be able to see.
                    self.permission_denied(self.request)
            else:
                qs = qs.filter(active=True)

            # Handle 'fxos_version' filtering if necessary.
            if fxos_version_parameter:
                qs = qs.filter(fxos_version=fxos_version_parameter)
        return qs

    def get_serializer_class(self):
        if self.request.method in ('POST', 'PUT'):
            # When using POST or PUT, we are uploading a new package.
            return LangPackUploadSerializer
        else:
            return LangPackSerializer


@allow_cross_site_request
def manifest(request, uuid):
    """Returns the "mini" manifest for a langpack."""
    try:
        uuid_hex = UUID(uuid).hex
    except ValueError:
        raise Http404

    langpack = get_object_or_404(LangPack, pk=uuid_hex)

    if langpack.active or action_allowed(request, 'LangPacks', '%'):
        manifest_contents, langpack_etag = langpack.get_minifest_contents()

        @condition(last_modified_func=lambda request: langpack.modified,
                   etag_func=lambda request: langpack_etag)
        def _inner_view(request):
            return HttpResponse(manifest_contents,
                                content_type=MANIFEST_CONTENT_TYPE)
        return _inner_view(request)
    raise Http404


@allow_cross_site_request
def download(request, langpack_id, **kwargs):
    langpack = get_object_or_404(LangPack, pk=langpack_id)

    if langpack.active or action_allowed(request, 'LangPacks', '%'):
        log.info('Downloading package: %s from %s' % (
                 langpack.pk, langpack.file_path))
        langpack_etag = hashlib.sha256()
        langpack_etag.update(langpack.pk)
        langpack_etag.update(unicode(langpack.file_version))
        return HttpResponseSendFile(request, langpack.file_path,
                                    content_type='application/zip',
                                    etag=langpack_etag.hexdigest())
    else:
        raise Http404
