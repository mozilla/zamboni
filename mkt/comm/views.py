import os

from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404

import waffle
from rest_framework import status
from rest_framework.authentication import BaseAuthentication
from rest_framework.decorators import (api_view, authentication_classes,
                                       permission_classes)
from rest_framework.exceptions import ParseError
from rest_framework.fields import BooleanField
from rest_framework.filters import BaseFilterBackend, OrderingFilter
from rest_framework.mixins import (CreateModelMixin, DestroyModelMixin,
                                   ListModelMixin, RetrieveModelMixin)
from rest_framework.parsers import FormParser, JSONParser

from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet


from amo.decorators import skip_cache
from amo.utils import HttpResponseSendFile

import mkt.comm.forms as forms
import mkt.constants.comm as comm
from mkt.access import acl
from mkt.api.authentication import (RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.base import CORSMixin, MarketplaceView, SilentListModelMixin
from mkt.comm.authorization import (AttachmentPermission,
                                    EmailCreationPermission, NotePermission,
                                    ThreadPermission)
from mkt.comm.models import (CommAttachment, CommunicationNote,
                             CommunicationNoteRead, CommunicationThread,
                             CommunicationThreadCC)
from mkt.comm.serializers import NoteSerializer, ThreadSerializer
from mkt.comm.models import user_has_perm_app
from mkt.comm.tasks import consume_email, mark_thread_read
from mkt.comm.utils import (create_attachments, create_comm_note,
                            filter_notes_by_read_status)


class NoAuthentication(BaseAuthentication):
    def authenticate(self, request):
        return request._request.user, None


class ReadUnreadFilter(BaseFilterBackend):
    filter_param = 'show_read'

    def filter_queryset(self, request, queryset, view):
        """
        Return only read notes if `show_read=true` is truthy and only unread
        notes if `show_read=false.
        """
        val = request.GET.get('show_read')
        if val is None:
            return queryset

        show_read = BooleanField().from_native(val)
        return filter_notes_by_read_status(queryset, request.user,
                                           show_read)


class CommViewSet(CORSMixin, MarketplaceView, GenericViewSet):
    """Some overriding and mixin stuff to adapt other viewsets."""
    parser_classes = (FormParser, JSONParser)

    def patched_get_request(self):
        return lambda x: self.request

    def get_serializer_class(self):
        original = super(CommViewSet, self).get_serializer_class()
        original.get_request = self.patched_get_request()

        return original

    def partial_update(self, request, *args, **kwargs):
        val = BooleanField().from_native(request.DATA.get('is_read'))

        if val:
            self.mark_as_read(request.user)
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response('Requested update operation not supported',
                status=status.HTTP_403_FORBIDDEN)


class ThreadViewSet(SilentListModelMixin, RetrieveModelMixin,
                    DestroyModelMixin, CreateModelMixin, CommViewSet):
    model = CommunicationThread
    serializer_class = ThreadSerializer
    authentication_classes = (RestOAuthAuthentication,
                              RestSharedSecretAuthentication)
    permission_classes = (ThreadPermission,)
    filter_backends = (OrderingFilter,)
    cors_allowed_methods = ['get', 'post', 'patch']

    @skip_cache
    def list(self, request):
        self.serializer_class = ThreadSerializer
        profile = request.user
        # We list all the threads where the user has been CC'd.
        cc = list(profile.comm_thread_cc.values_list('thread', flat=True))

        # This gives 404 when an app with given slug/id is not found.
        data = {}
        if 'app' in request.GET:
            form = forms.AppSlugForm(request.GET)
            if not form.is_valid():
                return Response('App does not exist or no app slug given',
                                status=status.HTTP_404_NOT_FOUND)
            elif not user_has_perm_app(profile, form.cleaned_data['app']):
                return Response('You do not have permissions for this app',
                                status=status.HTTP_403_FORBIDDEN)

            queryset = CommunicationThread.objects.filter(
                addon=form.cleaned_data['app'])

            # Thread IDs and version numbers from same app.
            data['app_threads'] = list(queryset.order_by('version__version')
                .values('id', 'version__version'))
        else:
            # We list all the threads that user is developer of or
            # is subscribed/CC'ed to.
            addons = list(profile.addons.values_list('pk', flat=True))
            q_dev = Q(addon__in=addons, read_permission_developer=True)
            queryset = CommunicationThread.objects.filter(
                Q(pk__in=cc) | q_dev)

        self.queryset = queryset
        res = SilentListModelMixin.list(self, request)
        if res.data:
            res.data.update(data)

        return res

    def retrieve(self, *args, **kwargs):
        res = super(ThreadViewSet, self).retrieve(*args, **kwargs)

        # Thread IDs and version numbers from same app.
        res.data['app_threads'] = list(
            CommunicationThread.objects.filter(addon_id=res.data['addon'])
            .order_by('version__version').values('id', 'version__version'))
        return res

    def create(self, request, *args, **kwargs):
        if not waffle.switch_is_active('comm-dashboard'):
            return Response(status=status.HTTP_403_FORBIDDEN)

        form = forms.CreateCommThreadForm(request.DATA)
        if not form.is_valid():
            return Response(
                form.errors, status=status.HTTP_400_BAD_REQUEST)

        app = form.cleaned_data['app']
        version = form.cleaned_data['version']
        thread, note = create_comm_note(
            app, version, request.user, form.cleaned_data['body'],
            note_type=form.cleaned_data['note_type'])

        return Response(
            NoteSerializer(note, context={'request': self.request}).data,
            status=status.HTTP_201_CREATED)

    def mark_as_read(self, profile):
        mark_thread_read(self.get_object(), profile)


class NoteViewSet(ListModelMixin, CreateModelMixin, RetrieveModelMixin,
                  DestroyModelMixin, CommViewSet):
    model = CommunicationNote
    serializer_class = NoteSerializer
    authentication_classes = (RestOAuthAuthentication,
                              RestSharedSecretAuthentication)
    permission_classes = (NotePermission,)
    filter_backends = (OrderingFilter, ReadUnreadFilter)
    cors_allowed_methods = ['get', 'patch', 'post']

    def get_queryset(self):
        return CommunicationNote.objects.with_perms(
            self.request.user, self.comm_thread)

    def create(self, request, *args, **kwargs):
        if not waffle.switch_is_active('comm-dashboard'):
            return Response(status=status.HTTP_403_FORBIDDEN)

        thread = get_object_or_404(CommunicationThread, id=kwargs['thread_id'])

        # Validate note.
        form = forms.CreateCommNoteForm(request.DATA)
        if not form.is_valid():
            return Response(form.errors, status=status.HTTP_400_BAD_REQUEST)
        note_type = form.cleaned_data['note_type']

        if (note_type == comm.DEVELOPER_COMMENT and not
            request.user.addonuser_set.filter(
                addon=thread.addon).exists()):
            # Developer comment only for developers.
            return Response('Only developers can make developer comments',
                            status=status.HTTP_403_FORBIDDEN)
        elif (note_type == comm.REVIEWER_COMMENT and not
              acl.check_reviewer(request)):
            # Reviewer comment only for reviewers.
            return Response('Only reviewers can make reviewer comments',
                            status=status.HTTP_403_FORBIDDEN)

        # Create notes.
        thread, note = create_comm_note(
            thread.addon, thread.version, self.request.user,
            form.cleaned_data['body'], note_type=note_type)

        return Response(
            NoteSerializer(note, context={'request': request}).data,
            status=status.HTTP_201_CREATED)

    def mark_as_read(self, profile):
        CommunicationNoteRead.objects.get_or_create(note=self.get_object(),
            user=profile)


class AttachmentViewSet(CreateModelMixin, CommViewSet):
    model = CommAttachment
    authentication_classes = (RestOAuthAuthentication,
                              RestSharedSecretAuthentication)
    permission_classes = (AttachmentPermission,)
    cors_allowed_methods = ['get', 'post']

    def get(self, request, note_id, pk, *args, **kwargs):
        attach = get_object_or_404(CommAttachment, pk=pk)
        self.check_object_permissions(request, attach)

        full_path = os.path.join(settings.REVIEWER_ATTACHMENTS_PATH,
                                 attach.filepath)

        content_type = 'application/force-download'
        if attach.is_image():
            content_type = 'image'
        return HttpResponseSendFile(
            request, full_path, content_type=content_type)

    def create(self, request, note_id, *args, **kwargs):
        note = get_object_or_404(CommunicationNote, id=note_id)
        if not note.author.id == request.user.id:
            return Response(
                [{'non_field_errors':
                  'You must be owner of the note to attach a file.'}],
                status=status.HTTP_403_FORBIDDEN)

        # Validate attachment.
        attachment_formset = None
        if request.FILES:
            data = request.POST.copy()
            data.update({
                'form-TOTAL_FORMS': len([k for k in request.FILES if
                                         k.endswith('-attachment')]),
                'form-INITIAL_FORMS': 0,
                'form-MAX_NUM_FORMS': comm.MAX_ATTACH
            })

            if data['form-TOTAL_FORMS'] > comm.MAX_ATTACH:
                # TODO: use formset validate_max=True in Django 1.6.
                return Response(
                    [{'non_field_errors':
                      'Maximum of %s files can be attached.'}],
                    status=status.HTTP_400_BAD_REQUEST)

            attachment_formset = forms.CommAttachmentFormSet(
                data=data, files=request.FILES or None)
            if not attachment_formset.is_valid():
                return Response(attachment_formset.errors,
                                status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response([{'non_field_errors': 'No files were attached.'}],
                            status=status.HTTP_400_BAD_REQUEST)

        # Create attachment.
        if attachment_formset:
            create_attachments(note, attachment_formset)

        return Response(
            NoteSerializer(note, context={'request': request}).data,
            status=status.HTTP_201_CREATED)

    def mark_as_read(self, profile):
        CommunicationNoteRead.objects.get_or_create(note=self.get_object(),
            user=profile)


class ThreadCCViewSet(DestroyModelMixin, CommViewSet):
    model = CommunicationThreadCC
    authentication_classes = (RestOAuthAuthentication,
                              RestSharedSecretAuthentication)
    permission_classes = ()
    cors_allowed_methods = ['delete']

    def destroy(self, request, **kw):
        form = forms.UnCCForm(kw)
        if not form.is_valid():
            return Response(status=status.HTTP_400_BAD_REQUEST)

        CommunicationThreadCC.objects.filter(
            thread=form.cleaned_data['pk'],
            user=request.user).delete()

        return Response("Successfully un-cc'ed from thread.",
                        status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
@authentication_classes((NoAuthentication,))
@permission_classes((EmailCreationPermission,))
def post_email(request):
    email_body = request.POST.get('body')
    if not email_body:
        raise ParseError(
            detail='email_body not present in the POST data.')

    consume_email.apply_async((email_body,))
    return Response(status=status.HTTP_201_CREATED)
