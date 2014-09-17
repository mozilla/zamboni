import logging

from django.conf import settings
from django.core.files.storage import get_storage_class

from mkt.comm.utils_mail import send_mail_comm
from mkt.constants import comm
from mkt.users.models import UserProfile


log = logging.getLogger('z.comm')


def create_comm_note(app, version, author, body, note_type=comm.NO_ACTION,
                     perms=None, attachments=None):
    """
    Creates a note on an app version's thread.
    Creates a thread if a thread doesn't already exist.
    CC's app's Mozilla contacts to auto-join thread.

    app -- app object.
    version -- app version.
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

    # Create thread + note.
    thread, created_thread = app.threads.safer_get_or_create(
        version=version, defaults=create_perms)
    note = thread.notes.create(
        note_type=note_type, body=body, author=author, **create_perms)

    if attachments:
        create_attachments(note, attachments)

    post_create_comm_note(note)

    return thread, note


def post_create_comm_note(note):
    """Stuff to do after creating note, also used in comm api's post_save."""
    thread = note.thread
    app = thread.addon

    # Add developer to thread.
    for developer in app.authors.all():
        thread.join_thread(developer)

    # Add Mozilla contact to thread.
    for email in app.get_mozilla_contacts():
        try:
            moz_contact = UserProfile.objects.get(email=email)
            thread.join_thread(moz_contact)
        except UserProfile.DoesNotExist:
            pass

    # Add note author to thread.
    author = note.author
    if author:
        cc, created_cc = thread.join_thread(author)

    # Send out emails.
    send_mail_comm(note)


def create_attachments(note, formset):
    """Create attachments from CommAttachmentFormSet onto note."""
    errors = []
    storage = get_storage_class()()

    for form in formset:
        if not form.is_valid():
            errors.append(form.errors)
            continue

        data = form.cleaned_data
        if not data:
            continue

        attachment = data['attachment']
        attachment_name = _save_attachment(
            storage, attachment,
            '%s/%s' % (settings.REVIEWER_ATTACHMENTS_PATH, attachment.name))

        note.attachments.create(
            description=data.get('description'), filepath=attachment_name,
            mimetype=attachment.content_type)

    return errors


def _save_attachment(storage, attachment, filepath):
    """Saves an attachment and returns the filename."""
    filepath = storage.save(filepath, attachment)
    # In case of duplicate filename, storage suffixes filename.
    return filepath.split('/')[-1]
