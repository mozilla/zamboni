from django import forms as django_forms
from django.core.urlresolvers import reverse
from django.http import Http404

import commonware
from rest_framework import exceptions, response, serializers, status, viewsets
from rest_framework.decorators import detail_route
from rest_framework.response import Response

from lib.metrics import record_action
from mkt.api.authentication import (RestAnonymousAuthentication,
                                    RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.base import CORSMixin, MarketplaceView, SlugOrIdMixin
from mkt.api.exceptions import HttpLegallyUnavailable
from mkt.api.forms import IconJSONForm
from mkt.api.permissions import (AllowAppOwner, AllowReadOnlyIfPublic,
                                 AllowReviewerReadOnly, AnyOf)
from mkt.developers import tasks
from mkt.developers.forms import AppFormMedia
from mkt.files.models import FileUpload
from mkt.regions import get_region
from mkt.submit.views import PreviewViewSet
from mkt.webapps.models import AddonUser, get_excluded_in, Webapp
from mkt.webapps.serializers import AppSerializer


log = commonware.log.getLogger('z.api')


class AppViewSet(CORSMixin, SlugOrIdMixin, MarketplaceView,
                 viewsets.ModelViewSet):
    serializer_class = AppSerializer
    slug_field = 'app_slug'
    cors_allowed_methods = ('get', 'put', 'post', 'delete')
    permission_classes = [AnyOf(AllowAppOwner, AllowReviewerReadOnly,
                                AllowReadOnlyIfPublic)]
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]

    def get_queryset(self):
        return Webapp.objects.all().exclude(
            id__in=get_excluded_in(get_region().id))

    def get_base_queryset(self):
        return Webapp.objects.all()

    def get_object(self):
        try:
            app = super(AppViewSet, self).get_object()
        except Http404:
            self.get_queryset = self.get_base_queryset
            app = super(AppViewSet, self).get_object()
            # Owners and reviewers can see apps regardless of region.
            owner_or_reviewer = AnyOf(AllowAppOwner, AllowReviewerReadOnly)
            if owner_or_reviewer.has_object_permission(self.request, self,
                                                       app):
                return app
            data = {}
            for key in ('name', 'support_email', 'support_url'):
                value = getattr(app, key)
                data[key] = unicode(value) if value else ''
            data['reason'] = 'Not available in your region.'
            raise HttpLegallyUnavailable(data)
        self.check_object_permissions(self.request, app)
        return app

    def create(self, request, *args, **kwargs):
        uuid = request.data.get('upload', '')
        if uuid:
            is_packaged = True
        else:
            uuid = request.data.get('manifest', '')
            is_packaged = False
        if not uuid:
            raise exceptions.ParseError(
                'No upload or manifest specified.')

        try:
            upload = FileUpload.objects.get(uuid=uuid)
        except FileUpload.DoesNotExist:
            raise exceptions.ParseError('No upload found.')
        if not upload.valid:
            raise exceptions.ParseError('Upload not valid.')

        if not request.user.read_dev_agreement:
            log.info(u'Attempt to use API without dev agreement: %s'
                     % request.user.pk)
            raise exceptions.PermissionDenied('Terms of Service not accepted.')
        if not (upload.user and upload.user.pk == request.user.pk):
            raise exceptions.PermissionDenied('You do not own that app.')

        # Create app, user and fetch the icon.
        try:
            obj = Webapp.from_upload(upload, is_packaged=is_packaged)
        except (serializers.ValidationError,
                django_forms.ValidationError) as e:
            raise exceptions.ParseError(unicode(e))
        AddonUser(addon=obj, user=request.user).save()
        tasks.fetch_icon.delay(obj.pk, obj.latest_version.all_files[0].pk)
        record_action('app-submitted', request, {'app-id': obj.pk})
        log.info('App created: %s' % obj.pk)
        data = AppSerializer(
            context=self.get_serializer_context(), instance=obj).data

        return response.Response(
            data, status=201,
            headers={'Location': reverse('app-detail', kwargs={'pk': obj.pk})})

    def update(self, request, *args, **kwargs):
        # Fail if the app doesn't exist yet.
        self.get_object()
        r = super(AppViewSet, self).update(request, *args, **kwargs)
        # Be compatible with tastypie responses.
        if r.status_code == 200:
            r.status_code = 202
        return r

    def list(self, request, *args, **kwargs):
        if not request.user.is_authenticated():
            log.info('Anonymous listing not allowed')
            raise exceptions.PermissionDenied('Anonymous listing not allowed.')

        self.object_list = self.filter_queryset(self.get_queryset().filter(
            authors=request.user))
        page = self.paginate_queryset(self.object_list)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        raise exceptions.MethodNotAllowed('PATCH')

    @detail_route(
        methods=['POST'],
        cors_allowed_methods=PreviewViewSet.cors_allowed_methods)
    def preview(self, request, *args, **kwargs):
        kwargs['app'] = self.get_object()
        view = PreviewViewSet.as_view({'post': '_create'})
        return view(request, *args, **kwargs)

    @detail_route(methods=['PUT'], cors_allowed_methods=['put'])
    def icon(self, request, *args, **kwargs):
        app = self.get_object()

        data_form = IconJSONForm(request.data)
        if not data_form.is_valid():
            return Response(data_form.errors,
                            status=status.HTTP_400_BAD_REQUEST)

        form = AppFormMedia(data_form.cleaned_data, request=request)
        if not form.is_valid():
            return Response(data_form.errors,
                            status=status.HTTP_400_BAD_REQUEST)

        form.save(app)
        return Response(status=status.HTTP_200_OK)


class PrivacyPolicyViewSet(CORSMixin, SlugOrIdMixin, MarketplaceView,
                           viewsets.GenericViewSet):
    queryset = Webapp.objects.all()
    cors_allowed_methods = ('get',)
    permission_classes = [AnyOf(AllowAppOwner, AllowReviewerReadOnly,
                                AllowReadOnlyIfPublic)]
    slug_field = 'app_slug'
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]

    def retrieve(self, request, *args, **kwargs):
        app = self.get_object()
        return response.Response(
            {'privacy_policy': unicode(app.privacy_policy)},
            content_type='application/json')
