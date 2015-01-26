# -*- coding: utf-8 -*-
import commonware
from rest_framework import viewsets

from mkt.access.acl import action_allowed
from mkt.api.authentication import (RestAnonymousAuthentication,
                                    RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.authorization import (AllowReadOnlyIfPublic, AnyOf,
                                   GroupPermission)
from mkt.api.base import CORSMixin, MarketplaceView
from mkt.langpacks.models import LangPack
from mkt.langpacks.serializers import (LangPackSerializer,
                                       LangPackUploadSerializer)


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
            has_permission = action_allowed(self.request, 'LangPacks', '%')

            if 'pk' in self.kwargs and has_permission:
                # No filtering at all if we're trying to see a detail page and
                # we have the permission to show everything.
                return qs
            elif active_parameter in ('null', 'false'):
                if has_permission:
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
        return qs

    def get_serializer_class(self):
        if self.request.method in ('POST', 'PUT'):
            # When using POST or PUT, we are uploading a new package.
            return LangPackUploadSerializer
        else:
            return LangPackSerializer
