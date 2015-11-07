import imghdr
import os
from datetime import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse
from django.db import models
from django.utils.safestring import mark_safe

import bleach
from uuidfield.fields import UUIDField

from mkt.access import acl
from mkt.constants import comm
from mkt.extensions.models import Extension
from mkt.site.models import ModelBase
from mkt.translations.fields import save_signal
from mkt.webapps.models import AddonUser, Webapp


class CommunicationPermissionModel(ModelBase):
    # Read permissions imply write permissions as well.
    read_permission_public = models.BooleanField(default=False)
    read_permission_developer = models.BooleanField(default=True)
    read_permission_reviewer = models.BooleanField(default=True)
    read_permission_senior_reviewer = models.BooleanField(default=True)
    read_permission_mozilla_contact = models.BooleanField(default=True)
    read_permission_staff = models.BooleanField(default=True)

    class Meta:
        abstract = True


def check_acls(user, obj, acl_type):
    """Check ACLs."""
    if acl_type == 'moz_contact':
        try:
            return user.email in obj.addon.get_mozilla_contacts()
        except AttributeError:
            try:
                return user.email in obj.thread.addon.get_mozilla_contacts()
            except AttributeError:
                return False
    elif acl_type == 'admin':
        return acl.action_allowed_user(user, 'Admin', '%')
    elif acl_type == 'reviewer':
        return (acl.action_allowed_user(user, 'Apps', 'Review') or
                acl.action_allowed_user(user, 'ContentTools', 'AddonReview'))
    elif acl_type == 'senior_reviewer':
        return acl.action_allowed_user(user, 'Apps', 'ReviewEscalated')
    else:
        raise Exception('Invalid ACL lookup.')
    return False


def check_acls_comm_obj(obj, profile):
    """Cross-reference ACLs and Note/Thread permissions."""
    if obj.read_permission_public:
        return True

    if (obj.read_permission_reviewer and
            check_acls(profile, obj, 'reviewer')):
        return True

    if (obj.read_permission_senior_reviewer and
            check_acls(profile, obj, 'senior_reviewer')):
        return True

    if (obj.read_permission_mozilla_contact and
            check_acls(profile, obj, 'moz_contact')):
        return True

    if (obj.read_permission_staff and
            check_acls(profile, obj, 'admin')):
        return True

    return False


def user_has_perm_app(user, obj):
    """
    It's named `app` for historical reasons, but it `obj` can be either a
    Webapp or Extension.

    Check if user has any app-level ACLs.
    (Mozilla contact, admin, review, senior reviewer, developer).
    """
    # grep: comm-content-type.
    has_perm = False
    if obj.__class__ == Webapp:
        has_perm = (user.addons.filter(pk=obj.id).exists() or
                    user.email in obj.get_mozilla_contacts())
    elif obj.__class__ == Extension:
        has_perm = user.extension_set.filter(pk=obj.id).exists()

    return (
        has_perm or
        check_acls(user, None, 'reviewer') or
        check_acls(user, None, 'senior_reviewer') or
        check_acls(user, None, 'admin')
    )


def user_has_perm_thread(thread, profile):
    """
    Check if the user has read/write permissions on the given thread.

    Developers of the add-on used in the thread, users in the CC list,
    and users who post to the thread are allowed to access the object.

    Moreover, other object permissions are also checked against the ACLs
    of the user.
    """
    user_post = CommunicationNote.objects.filter(
        author=profile, thread=thread)
    user_cc = CommunicationThreadCC.objects.filter(
        user=profile, thread=thread)

    if user_post.exists() or user_cc.exists():
        return True

    if thread.read_permission_developer and thread.check_obj_author(profile):
        # Developers have permissions to their own threads.
        return True

    return check_acls_comm_obj(thread, profile)


def user_has_perm_note(note, profile, request=None):
    """
    Check if the user has read/write permissions on the given note.

    Developers of the add-on used in the note, users in the CC list,
    and users who post to the thread are allowed to access the object.

    Moreover, other object permissions are also checked against the ACLs
    of the user.
    """
    if note.author and note.author.id == profile.id:
        # Let the person access their own note.
        return True

    if request and note.note_type == comm.REVIEWER_COMMENT:
        # Internal reviewer comment only for reviewers.
        return acl.check_reviewer(request)

    if (request and note.note_type == comm.DEVELOPER_COMMENT and
            acl.check_reviewer(request)):
        # Reviewers can see developer comments.
        return True

    # User is a developer of the add-on and has the permission to read.
    user_is_author = profile.addons.filter(pk=note.thread._addon_id)
    if (user_is_author.exists() and
            note.read_permission_developer or
            note.note_type == comm.REVIEWER_PUBLIC_COMMENT):
        return True

    return check_acls_comm_obj(note, profile)


class CommunicationThread(CommunicationPermissionModel):
    """
    Works for both apps (which are incorrectly named add-ons for historical
    reasons), and Firefox OS add-ons (which are named extensions). Got it?
    """
    _addon = models.ForeignKey('webapps.Webapp', related_name='threads',
                               db_column='addon_id', null=True)
    _version = models.ForeignKey('versions.Version', related_name='threads',
                                 db_column='version_id', null=True)

    _extension = models.ForeignKey(
        'extensions.Extension', related_name='threads',
        db_column='_extension_id', null=True)
    _extension_version = models.ForeignKey(
        'extensions.ExtensionVersion', related_name='threads',
        db_column='extension_version_id', null=True)

    class Meta:
        db_table = 'comm_threads'
        unique_together = (
            ('_addon', '_version'),
            ('_extension', '_extension_version'),
        )

    def clean(self):
        """Check at least has one of each foreign key."""
        if not self._addon and not self._extension:
            raise ValidationError(
                'One of _addon or _extension required')

        if not self._version and not self._extension_version:
            raise ValidationError(
                'One of _version or _extension_version required')

    @property
    def obj(self):
        """
        Returns either the add-on or extension depending on the type of the
        thread.
        """
        # grep: comm-content-type.
        if self._addon_id:
            from mkt.webapps.models import Webapp
            return Webapp.with_deleted.get(pk=self._addon_id)
        elif self._extension_id:
            return self._extension

    @property
    def addon(self):
        """
        TODO: get rid of all references to thread.addon.
        """
        return self.obj

    @property
    def version(self):
        """
        Returns either the add-on or extension depending on the type of the
        thread.
        """
        # grep: comm-content-type.
        if self._version_id:
            from mkt.versions.models import Version
            return Version.with_deleted.get(pk=self._version_id)
        elif self._extension_version_id:
            return self._extension_version

    def check_obj_author(self, profile):
        """
        Check if profile is an author or developer of the obj this thread
        refers to, commonly used for permissions.
        """
        # grep: comm-content-type.
        if self.obj.__class__ == Webapp:
            return AddonUser.objects.filter(addon_id=self.obj.id,
                                            user=profile).exists()
        elif self.obj.__class__ == Extension:
            return profile.extension_set.filter(id=self.obj.id).exists()

    def join_thread(self, user):
        return self.thread_cc.get_or_create(user=user)


class CommunicationThreadCC(ModelBase):
    """
    Determines recipients of emails. Akin being joined on a thread.
    """
    thread = models.ForeignKey(CommunicationThread,
                               related_name='thread_cc')
    user = models.ForeignKey('users.UserProfile',
                             related_name='comm_thread_cc')

    class Meta:
        db_table = 'comm_thread_cc'
        unique_together = ('user', 'thread',)


class CommunicationNoteManager(models.Manager):

    def with_perms(self, profile, thread):
        ids = [note.id for note in self.filter(thread=thread) if
               user_has_perm_note(note, profile)]
        return self.filter(id__in=ids)


class CommunicationNote(CommunicationPermissionModel):
    thread = models.ForeignKey(CommunicationThread, related_name='notes')
    author = models.ForeignKey('users.UserProfile', related_name='comm_notes',
                               null=True, blank=True)
    note_type = models.IntegerField(default=comm.NO_ACTION)
    body = models.TextField(null=True)

    objects = CommunicationNoteManager()

    class Meta:
        db_table = 'comm_thread_notes'

    def save(self, *args, **kwargs):
        super(CommunicationNote, self).save(*args, **kwargs)
        self.thread.modified = self.created
        self.thread.save()


class CommAttachment(ModelBase):
    """
    Model for an attachment to an CommNote instance. Used by the Marketplace
    reviewer tools, where reviewers can attach files to comments made during
    the review process.
    """
    note = models.ForeignKey('CommunicationNote', related_name='attachments')
    filepath = models.CharField(max_length=255)
    description = models.CharField(max_length=255, blank=True)
    mimetype = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = 'comm_attachments'
        ordering = ('id',)

    def __unicode__(self):
        return 'Note %s - %s' % (self.note.id, self.filepath)

    def get_absolute_url(self):
        return reverse('comm-attachment-detail', args=[self.note_id, self.pk])

    def filename(self):
        """Returns the attachment's file name."""
        return os.path.basename(self.filepath)

    def full_path(self):
        """Returns the full filesystem path of the attachment."""
        try:
            return os.path.join(settings.REVIEWER_ATTACHMENTS_PATH,
                                self.filepath)
        except IOError:
            if not settings.DEBUG:
                raise

    def display_name(self):
        """
        Returns a string describing the attachment suitable for front-end
        display.
        """
        display = self.description if self.description else self.filename()
        return mark_safe(bleach.clean(display))

    def is_image(self):
        """
        Returns a boolean indicating whether the attached file is an image of a
        format recognizable by the stdlib imghdr module.
        """
        try:
            return imghdr.what(self.full_path()) is not None
        except IOError:
            if not settings.DEBUG:
                raise


class CommunicationThreadToken(ModelBase):
    thread = models.ForeignKey(CommunicationThread, related_name='token')
    user = models.ForeignKey('users.UserProfile',
                             related_name='comm_thread_tokens')
    uuid = UUIDField(unique=True, auto=True)
    use_count = models.IntegerField(
        default=0,
        help_text='Stores the number of times the token has been used')

    class Meta:
        db_table = 'comm_thread_tokens'
        unique_together = ('thread', 'user')

    def is_valid(self):
        # TODO: Confirm the expiration and max use count values.
        timedelta = datetime.now() - self.modified
        return (timedelta.days <= comm.THREAD_TOKEN_EXPIRY and
                self.use_count < comm.MAX_TOKEN_USE_COUNT)

    def reset_uuid(self):
        # Generate a new UUID.
        self.uuid = UUIDField()._create_uuid().hex


models.signals.pre_save.connect(save_signal, sender=CommunicationNote,
                                dispatch_uid='comm_thread_notes_translations')
