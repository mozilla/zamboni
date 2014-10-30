import logging
from celeryutils import task

import mkt.constants.comm as cmb
from mkt.comm.models import CommunicationNote, CommunicationThread
from mkt.comm.utils_mail import save_from_email_reply
from mkt.developers.models import ActivityLog
from mkt.site.decorators import write
from mkt.versions.models import Version


log = logging.getLogger('z.task')


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

        action = cmb.ACTION_MAP(log.action)

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
            read_permission_developer=action not in cmb.REVIEWER_NOTE_TYPES,
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
            note_type=cmb.DEVELOPER_VERSION_NOTE_FOR_REVIEWER).exists()):
            # Don't need to do if it's already been done.
            continue

        note = thread.notes.create(
            # Close enough. Don't want to dig through logs to get correct dev.
            author=version.addon.authors.all()[0],
            note_type=cmb.DEVELOPER_VERSION_NOTE_FOR_REVIEWER,
            body=version.approvalnotes)
        note.update(created=version.created)
