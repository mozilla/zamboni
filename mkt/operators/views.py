from django.shortcuts import render

from rest_framework import mixins, response, status, viewsets
from waffle.decorators import waffle_switch

import amo
from amo.utils import paginate
from mkt.access import acl
from mkt.api.base import CORSMixin
from mkt.api.authentication import (RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.developers.models import PreloadTestPlan
from mkt.site.decorators import permission_required
from mkt.users.models import UserProfile

from .models import OperatorPermission
from .serializers import OperatorPermissionSerializer


@permission_required([('Operators', '*')])
@waffle_switch('preload-apps')
def preloads(request):
    preloads = (PreloadTestPlan.objects.filter(status=amo.STATUS_PUBLIC)
                                       .order_by('-created'))
    preloads = paginate(request, preloads, per_page=20)

    return render(request, 'operators/preloads.html', {'preloads': preloads})


class OperatorPermissionViewSet(CORSMixin, mixins.ListModelMixin,
                                viewsets.GenericViewSet):
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication]
    cors_allowed_methods = ('GET',)
    queryset = OperatorPermission.objects.all()
    permission_classes = []
    serializer_class = OperatorPermissionSerializer

    def get_queryset(self):
        if isinstance(self.request.user, UserProfile):
            return self.queryset.filter(user=self.request.user)
        return self.queryset.none()

    def list(self, request, *args, **kwargs):
        if acl.action_allowed(request, 'OperatorDashboard', '*'):
            return response.Response(['*'], status=status.HTTP_200_OK)
        return super(OperatorPermissionViewSet, self).list(
            request, *args, **kwargs)
