import logging

from django.conf import settings

from mkt.comm import utils_mail
from mkt.constants import comm
from mkt.extensions.models import Extension
from mkt.users.models import UserProfile
from mkt.site.storage_utils import private_storage
from mkt.webapps.models import Webapp


log = logging.getLogger('z.comm')


def create_comm_note(obj, version, author, body, note_type=comm.NO_ACTION,
                     perms=None, attachments=None):
    """
    Creates a note on an obj version's thread.
    Creates a thread if a thread doesn't already exist.
    CC's app's Mozilla contacts to auto-join thread.

    obj -- app or extension.
    version -- obj version.
    author -- UserProfile for the note's author.
    body -- string/text for note comment.
    note_type -- integer for note_type (mkt constant), defaults to 0/NO_ACTION
                 (e.g. comm.APPROVAL, comm.REJECTION, comm.NO_ACTION).
    perms -- object of groups to grant permission to, will set flags on Thread.
             (e.g. {'developer': False, 'staff': True}).
    attachments -- formset of attachment files
    """
    # Perm for reviewer, senior_reviewer, moz_contact, staff True by default.
    # Perm for developer False if is reviewer-only comment by default.
    perms = perms or {}
    if 'developer' not in perms and note_type in comm.REVIEWER_NOTE_TYPES:
        perms['developer'] = False
    create_perms = dict(('read_permission_%s' % key, has_perm)
                        for key, has_perm in perms.iteritems())

    # Differentiate between app and extension.
    # grep: comm-content-type.
    version_param = {}
    if obj.__class__ == Webapp:
        version_param['_version'] = version
    elif obj.__class__ == Extension:
        version_param['_extension_version'] = version

    # Create thread + note.
    thread, created_thread = obj.threads.safer_get_or_create(
        defaults=create_perms, **version_param)
    note = thread.notes.create(
        note_type=note_type, body=body, author=author, **create_perms)

    if attachments:
        create_attachments(note, attachments)

    post_create_comm_note(note)

    return thread, note


def post_create_comm_note(note):
    """Stuff to do after creating note, also used in comm api's post_save."""
    thread = note.thread
    obj = thread.obj

    # Add developer to thread.
    for developer in obj.authors.all():
        thread.join_thread(developer)

    try:
        # Add Mozilla contact to thread.
        nonuser_mozilla_contacts = []
        for email in obj.get_mozilla_contacts():
            try:
                moz_contact = UserProfile.objects.get(email=email)
                thread.join_thread(moz_contact)
            except UserProfile.DoesNotExist:
                nonuser_mozilla_contacts.append((None, email))
        utils_mail.email_recipients(
            nonuser_mozilla_contacts, note,
            extra_context={'nonuser_mozilla_contact': True})
    except AttributeError:
        # Only apps have Mozilla contacts.
        pass

    # Add note author to thread.
    author = note.author
    if author:
        cc, created_cc = thread.join_thread(author)

    # Send out emails.
    utils_mail.send_mail_comm(note)


def create_attachments(note, formset):
    """Create attachments from CommAttachmentFormSet onto note."""
    errors = []

    for form in formset:
        if not form.is_valid():
            errors.append(form.errors)
            continue

        data = form.cleaned_data
        if not data:
            continue

        attachment = data['attachment']
        attachment_name = _save_attachment(
            attachment, '%s/%s' % (settings.REVIEWER_ATTACHMENTS_PATH,
                                   attachment.name))

        note.attachments.create(
            description=data.get('description'), filepath=attachment_name,
            mimetype=attachment.content_type)

    return errors


def _save_attachment(attachment, filepath):
    """Saves an attachment and returns the filename."""
    filepath = private_storage.save(filepath, attachment)
    # In case of duplicate filename, storage suffixes filename.
    return filepath.split('/')[-1]
