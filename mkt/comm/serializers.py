import hashlib

from django.core.urlresolvers import reverse

from rest_framework.fields import BooleanField, CharField
from rest_framework.serializers import ModelSerializer, SerializerMethodField

from amo.helpers import absolutify
from mkt.comm.models import (CommAttachment, CommunicationNote,
                             CommunicationThread)
from mkt.versions.models import Version
from mkt.webapps.models import Addon
from mkt.users.models import UserProfile


class AuthorSerializer(ModelSerializer):
    gravatar_hash = SerializerMethodField('get_gravatar_hash')
    name = CharField()

    class Meta:
        model = UserProfile
        fields = ('gravatar_hash', 'name')

    def get_gravatar_hash(self, obj):
        return hashlib.md5(obj.email.lower()).hexdigest()


class AttachmentSerializer(ModelSerializer):
    url = SerializerMethodField('get_absolute_url')
    display_name = CharField(source='display_name')
    is_image = BooleanField(source='is_image')

    def get_absolute_url(self, obj):
        return absolutify(obj.get_absolute_url())

    class Meta:
        model = CommAttachment
        fields = ('id', 'created', 'url', 'display_name', 'is_image')


class NoteSerializer(ModelSerializer):
    body = CharField()
    author_meta = AuthorSerializer(source='author', read_only=True)
    is_read = SerializerMethodField('is_read_by_user')
    attachments = AttachmentSerializer(source='attachments', read_only=True)

    def is_read_by_user(self, obj):
        return obj.read_by_users.filter(
            pk=self.context['request'].user.id).exists()

    class Meta:
        model = CommunicationNote
        fields = ('id', 'created', 'attachments', 'author', 'author_meta',
                  'body', 'is_read', 'note_type', 'thread')


class AddonSerializer(ModelSerializer):
    name = CharField()
    thumbnail_url = SerializerMethodField('get_icon')
    url = CharField(source='get_absolute_url')
    review_url = SerializerMethodField('get_review_url')

    class Meta:
        model = Addon
        fields = ('id', 'name', 'url', 'thumbnail_url', 'app_slug', 'slug',
                  'review_url')

    def get_icon(self, app):
        return app.get_icon_url(64)

    def get_review_url(self, obj):
        return reverse('reviewers.apps.review', args=[obj.app_slug])


class ThreadSerializer(ModelSerializer):
    addon_meta = AddonSerializer(source='addon', read_only=True)
    recent_notes = SerializerMethodField('get_recent_notes')
    notes_count = SerializerMethodField('get_notes_count')
    version_number = SerializerMethodField('get_version_number')
    version_is_obsolete = SerializerMethodField('get_version_is_obsolete')

    class Meta:
        model = CommunicationThread
        fields = ('id', 'addon', 'addon_meta', 'version', 'notes_count',
                  'recent_notes', 'created', 'modified', 'version_number',
                  'version_is_obsolete')
        view_name = 'comm-thread-detail'

    def get_recent_notes(self, obj):
        notes = (obj.notes.with_perms(self.get_request().user, obj)
                          .order_by('-created')[:5])
        return NoteSerializer(
            notes, many=True, context={'request': self.get_request()}).data

    def get_notes_count(self, obj):
        return (obj.notes.with_perms(self.get_request().user, obj)
                         .count())

    def get_version_number(self, obj):
        try:
            return Version.with_deleted.get(id=obj.version_id).version
        except Version.DoesNotExist:
            return ''

    def get_version_is_obsolete(self, obj):
        try:
            return Version.with_deleted.get(id=obj.version_id).deleted
        except Version.DoesNotExist:
            return True
