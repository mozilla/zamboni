from django import forms as django_forms
from django.core.urlresolvers import reverse
from django.http import Http404

import commonware
from rest_framework import exceptions, response, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

import amo
from lib.metrics import record_action
from mkt.api.authentication import (RestAnonymousAuthentication,
                                    RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.authorization import (AllowAppOwner, AllowReadOnlyIfPublic,
                                   AllowReviewerReadOnly, AnyOf)
from mkt.api.base import CORSMixin, MarketplaceView, SlugOrIdMixin
from mkt.api.exceptions import HttpLegallyUnavailable
from mkt.api.forms import IconJSONForm
from mkt.developers import tasks
from mkt.developers.forms import AppFormMedia, IARCGetAppInfoForm
from mkt.files.models import FileUpload, Platform
from mkt.regions import get_region
from mkt.submit.views import PreviewViewSet
from mkt.translations.query import order_by_translation
from mkt.webapps.models import Addon, AddonUser, get_excluded_in, Webapp
from mkt.webapps.serializers import AppSerializer


log = commonware.log.getLogger('z.api')


class BaseFilter(object):
    """
    Filters help generate querysets for add-on listings.

    You have to define ``opts`` on the subclass as a sequence of (key, title)
    pairs.  The key is used in GET parameters and the title can be used in the
    view.

    The chosen filter field is combined with the ``base`` queryset using
    the ``key`` found in request.GET.  ``default`` should be a key in ``opts``
    that's used if nothing good is found in request.GET.
    """

    def __init__(self, request, base, key, default, model=Addon):
        self.opts_dict = dict(self.opts)
        self.extras_dict = dict(self.extras) if hasattr(self, 'extras') else {}
        self.request = request
        self.base_queryset = base
        self.key = key
        self.model = model
        self.field, self.title = self.options(self.request, key, default)
        self.qs = self.filter(self.field)

    def options(self, request, key, default):
        """Get the (option, title) pair we want according to the request."""
        if key in request.GET and (request.GET[key] in self.opts_dict or
                                   request.GET[key] in self.extras_dict):
            opt = request.GET[key]
        else:
            opt = default
        if opt in self.opts_dict:
            title = self.opts_dict[opt]
        else:
            title = self.extras_dict[opt]
        return opt, title

    def all(self):
        """Get a full mapping of {option: queryset}."""
        return dict((field, self.filter(field)) for field in dict(self.opts))

    def filter(self, field):
        """Get the queryset for the given field."""
        filter = self._filter(field) & self.base_queryset
        order = getattr(self, 'order_%s' % field, None)
        if order:
            return order(filter)
        return filter

    def _filter(self, field):
        return getattr(self, 'filter_%s' % field)()

    def filter_created(self):
        return (self.model.objects.order_by('-created')
                .with_index(addons='created_type_idx'))

    def filter_name(self):
        return order_by_translation(self.model.objects.all(), 'name')


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

    def get_object(self, queryset=None):
        try:
            app = super(AppViewSet, self).get_object()
        except Http404:
            app = super(AppViewSet, self).get_object(self.get_base_queryset())
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
        uuid = request.DATA.get('upload', '')
        if uuid:
            is_packaged = True
        else:
            uuid = request.DATA.get('manifest', '')
            is_packaged = False
        if not uuid:
            raise serializers.ValidationError(
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
        plats = [Platform.objects.get(id=amo.PLATFORM_ALL.id)]

        # Create app, user and fetch the icon.
        obj = Webapp.from_upload(upload, plats, is_packaged=is_packaged)
        AddonUser(addon=obj, user=request.user).save()
        tasks.fetch_icon.delay(obj)
        record_action('app-submitted', request, {'app-id': obj.pk})

        log.info('App created: %s' % obj.pk)
        data = AppSerializer(
            context=self.get_serializer_context()).to_native(obj)

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
        serializer = self.get_pagination_serializer(page)
        return response.Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        raise exceptions.MethodNotAllowed('PATCH')

    @action()
    def content_ratings(self, request, *args, **kwargs):
        app = self.get_object()
        form = IARCGetAppInfoForm(data=request.DATA, app=app)

        if form.is_valid():
            try:
                form.save(app)
                return Response(status=status.HTTP_201_CREATED)
            except django_forms.ValidationError:
                pass

        return Response(form.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['POST'],
            cors_allowed_methods=PreviewViewSet.cors_allowed_methods)
    def preview(self, request, *args, **kwargs):
        kwargs['app'] = self.get_object()
        view = PreviewViewSet.as_view({'post': '_create'})
        return view(request, *args, **kwargs)

    @action(methods=['PUT'], cors_allowed_methods=['put'])
    def icon(self, request, *args, **kwargs):
        app = self.get_object()

        data_form = IconJSONForm(request.DATA)
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
