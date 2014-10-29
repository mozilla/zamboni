import logging
from celeryutils import task

from mkt.comm.models import CommunicationNote, CommunicationThread
from mkt.comm.utils_mail import save_from_email_reply
from mkt.constants import comm
from mkt.developers.models import ActivityLog
from mkt.site.decorators import write
from mkt.versions.models import Version


log = logging.getLogger('z.comm')


@task
def consume_email(email_text, **kwargs):
    """Parse emails and save notes."""
    log.debug('Comm email: ' + email_text)
    res = save_from_email_reply(email_text)
    if not res:
        log.error('Failed to save email.')


@task
@write
def _migrate_activity_log(ids, **kwargs):
    """For migrate_activity_log.py script."""
    for log in ActivityLog.objects.filter(pk__in=ids):
        action = comm.ACTION_MAP(log.action)

        # Create thread.
        try:
            thread, tc = CommunicationThread.objects.safer_get_or_create(
                addon=log.arguments[0], version=log.arguments[1])
        except IndexError:
            continue

        # Filter notes.
        note_params = {
            'thread': thread,
            'note_type': action,
            'author': log.user,
            'body': log.details.get('comments', '') if log.details else '',
        }
        notes = CommunicationNote.objects.filter(created=log.created,
                                                 **note_params)
        if notes.exists():
            # Note already exists, move on.
            continue

        # Create note.
        note = CommunicationNote.objects.create(
            # Developers should not see escalate/reviewer comments.
            read_permission_developer=action not in comm.REVIEWER_NOTE_TYPES,
            **note_params)
        note.update(created=log.created)

        # Attachments.
        if note.attachments.exists():
            # Already migrated. Continue.
            continue

        # Create attachments.
        for attachment in log.activitylogattachment_set.all():
            note_attachment = note.attachments.create(
                filepath=attachment.filepath, mimetype=attachment.mimetype,
                description=attachment.description)
            note_attachment.update(created=attachment.created)


@task
@write
def _migrate_approval_notes(ids):
    """
    Port Version.approvalnotes to
    CommunicationNote(note_type=DEVELOPER_VERSION_NOTE_TO_REVIEWER).

    Make the CommunicationNote.created the same time as the Version.created
    since approvalnotes are created upon creation of a version.
    """
    for version in Version.objects.filter(pk__in=ids):
        if not version.approvalnotes:
            continue

        try:
            thread = CommunicationThread.objects.get(version=version)
        except CommunicationThread.DoesNotExist:
            continue

        if (thread.notes.filter(
            note_type=comm.DEVELOPER_VERSION_NOTE_FOR_REVIEWER).exists()):
            # Don't need to do if it's already been done.
            continue

        note = thread.notes.create(
            # Close enough. Don't want to dig through logs to get correct dev.
            author=version.addon.authors.all()[0],
            note_type=comm.DEVELOPER_VERSION_NOTE_FOR_REVIEWER,
            body=version.approvalnotes)
        note.update(created=version.created)


@task
@write
def _fix_developer_version_notes(ids):
    """
    Fix developer version notes that were logged as reviewer comments.
    The strategy is to find all reviewer comments that were authored the
    developer of the app and changed them to be developer version notes for
    reviewers. And check that they are the first note of the thread, to be
    sure.
    """
    for note in CommunicationNote.objects.filter(pk__in=ids):
        if note.note_type != comm.REVIEWER_COMMENT:
            # Just to make sure, even though it's specified in management cmd.
            continue

        if (note.author.id not in
            note.thread.addon.authors.values_list('id', flat=True)):
            # Check that the note came from the developer since developer
            # version notes come from the developer.
            continue

        if note.thread.notes.order_by('created')[0].id != note.id:
            # Check that the note is the first note of the thread, because
            # all developer version notes are the first thing created upon
            # a new version's thread.
            continue

        # Good to update.
        note.update(note_type=comm.DEVELOPER_VERSION_NOTE_FOR_REVIEWER)
        log.debug('Comm note %s fixed to be developer version note' % note.id)
