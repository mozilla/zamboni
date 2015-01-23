 # -*- coding: utf-8 -*-
import commonware
from rest_framework import viewsets

from mkt.api.authentication import (RestAnonymousAuthentication,
                                    RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.authorization import (AllowReadOnlyIfPublic,
                                   AllowReviewerReadOnly, AnyOf,
                                   GroupPermission)
from mkt.api.base import CORSMixin, MarketplaceView
from mkt.langpacks.models import LangPack
from mkt.langpacks.serializers import (LangPackSerializer,
                                       LangPackUploadSerializer)


log = commonware.log.getLogger('z.api')



# Flow is similar to apps (FIXME: add this to docs/):
# - Submit your package through ValidationViewSet (authenticated)
# - With the same user, take the upload id and send it to the LangPackViewSet
#   create view (using POST)

class LangPackViewSet(CORSMixin, MarketplaceView, viewsets.ModelViewSet):
    model = LangPack
    cors_allowed_methods = ('get', 'post', 'put', 'patch', 'delete')
    permission_classes = [AnyOf(AllowReadOnlyIfPublic, AllowReviewerReadOnly,
                                GroupPermission('LangPacks', '%'))]
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]
    serializer_class = LangPackSerializer

    # Restrict to active only in get_queryset for listing ?

    def get_serializer_class(self):
        if self.request.method == 'POST' or self.request.method == 'PUT':
            # When using POST or PUT, we are uploading a new package.
            return LangPackUploadSerializer
        else:
            return LangPackSerializer
