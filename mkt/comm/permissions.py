from django.conf import settings
from django.shortcuts import get_object_or_404

from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied

from mkt.comm.models import (CommunicationNote, CommunicationThread,
                             user_has_perm_note, user_has_perm_thread)


class ThreadPermission(BasePermission):
    """
    Permission wrapper for checking if the authenticated user has the
    permission to view the thread.
    """

    def has_permission(self, request, view):
        # Let `has_object_permission` handle the permissions when we retrieve
        # an object.
        if view.action == 'retrieve':
            return True
        if not request.user.is_authenticated():
            raise PermissionDenied()

        return True

    def has_object_permission(self, request, view, obj):
        """
        Make sure we give correct permissions to read/write the thread.
        """
        if not request.user.is_authenticated() or obj.read_permission_public:
            return obj.read_permission_public

        return user_has_perm_thread(obj, request.user)


class NotePermission(ThreadPermission):

    def has_permission(self, request, view):
        thread_id = view.kwargs.get('thread_id')
        if not thread_id and view.kwargs.get('note_id'):
            note = CommunicationNote.objects.get(id=view.kwargs['note_id'])
            thread_id = note.thread_id

        # We save the thread in the view object so we can use it later.
        view.comm_thread = get_object_or_404(
            CommunicationThread, id=thread_id)

        return ThreadPermission.has_object_permission(
            self, request, view, view.comm_thread)

    def has_object_permission(self, request, view, obj):
        # Has thread obj-level permission AND note obj-level permission.
        return user_has_perm_note(obj, request.user)


class AttachmentPermission(NotePermission):

    def has_permission(self, request, view):
        note = CommunicationNote.objects.get(id=view.kwargs['note_id'])
        return NotePermission.has_object_permission(self, request, view, note)

    def has_object_permission(self, request, view, obj):
        # Has thread obj-level permission AND note obj-level permission.
        note = CommunicationNote.objects.get(id=view.kwargs['note_id'])
        return NotePermission.has_object_permission(self, request, view, note)


class EmailCreationPermission(object):
    """Permit if client's IP address is allowed."""

    def has_permission(self, request, view):
        auth_token = request.META.get('HTTP_POSTFIX_AUTH_TOKEN')
        if auth_token and auth_token not in settings.POSTFIX_AUTH_TOKEN:
            return False

        remote_ip = request.META.get('REMOTE_ADDR')
        return remote_ip and (
            remote_ip in settings.ALLOWED_CLIENTS_EMAIL_API)
