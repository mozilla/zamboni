import base64
import logging
import urllib2
from email import message_from_string
from email.utils import parseaddr

from django.conf import settings
from django.core.urlresolvers import reverse
from django.utils import translation

import waffle
from email_reply_parser import EmailReplyParser

import amo
from amo.utils import to_language

from mkt.access import acl
from mkt.access.models import Group
from mkt.comm.models import CommunicationThreadToken, user_has_perm_thread
from mkt.constants import comm
from mkt.site.helpers import absolutify
from mkt.site.mail import send_mail_jinja
from mkt.webapps.models import Webapp


log = logging.getLogger('z.comm')


def send_mail_comm(note):
    """
    Email utility used globally by the Communication Dashboard to send emails.
    Given a note (its actions and permissions), recipients are determined and
    emails are sent to appropriate people.
    """
    if not waffle.switch_is_active('comm-dashboard'):
        return

    recipients = get_recipients(note)
    name = note.thread.addon.name
    subject = '%s: %s' % (unicode(comm.NOTE_TYPES[note.note_type]), name)

    log.info(u'Sending emails for %s' % note.thread.addon)
    for email, tok in recipients:
        reply_to = '{0}{1}@{2}'.format(comm.REPLY_TO_PREFIX, tok,
                                       settings.POSTFIX_DOMAIN)

        # Get the appropriate mail template.
        mail_template = comm.COMM_MAIL_MAP.get(note.note_type, 'generic')
        # Send mail.
        send_mail_jinja(subject, 'comm/emails/%s.html' % mail_template,
                        get_mail_context(note), recipient_list=[email],
                        from_email=settings.MKT_REVIEWERS_EMAIL,
                        perm_setting='app_reviewed',
                        headers={'reply_to': reply_to})


def get_recipients(note):
    """
    Determine email recipients based on a new note based on those who are on
    the thread_cc list and note permissions.
    Returns reply-to-tokenized emails.
    """
    thread = note.thread
    recipients = []

    # Whitelist: include recipients.
    if note.note_type == comm.ESCALATION:
        # Email only senior reviewers on escalations.
        seniors = Group.objects.get(name='Senior App Reviewers')
        recipients = seniors.users.values_list('id', 'email')
    else:
        # Get recipients via the CommunicationThreadCC table, which is usually
        # populated with the developer, the Mozilla contact, and anyone that
        # posts to and reviews the app.
        recipients = set(thread.thread_cc.values_list(
            'user__id', 'user__email'))

    # Blacklist: exclude certain people from receiving the email based on
    # permission.
    excludes = []
    if not note.read_permission_developer:
        # Exclude developer.
        excludes += thread.addon.authors.values_list('id', 'email')

    if note.author:
        # Exclude note author.
        excludes.append((note.author.id, note.author.email))

    # Remove excluded people from the recipients.
    recipients = [r for r in recipients if r not in excludes]

    # Build reply-to-tokenized email addresses.
    new_recipients_list = []
    for user_id, user_email in recipients:
        tok = get_reply_token(note.thread, user_id)
        new_recipients_list.append((user_email, tok.uuid))

    return new_recipients_list


def get_mail_context(note):
    """
    Get context data for comm emails, specifically for review action emails.
    """
    app = note.thread.addon

    if app.name.locale != app.default_locale:
        # We need to display the name in some language that is relevant to the
        # recipient(s) instead of using the reviewer's. addon.default_locale
        # should work.
        lang = to_language(app.default_locale)
        with translation.override(lang):
            app = Webapp.objects.get(id=app.id)

    return {
        'amo': amo,
        'app': app,
        'comm': comm,
        'comments': note.body,
        'detail_url': absolutify(
            app.get_url_path(add_prefix=False)),
        'MKT_SUPPORT_EMAIL': settings.MKT_SUPPORT_EMAIL,
        'name': app.name,
        'note': note,
        'review_url': absolutify(reverse('reviewers.apps.review',
                                 args=[app.app_slug], add_prefix=False)),
        'reviewer': note.author,
        'sender': note.author.name if note.author else 'System',
        'SITE_URL': settings.SITE_URL,
        'status_url': absolutify(app.get_dev_url('versions')),
        'thread_id': str(note.thread.id)
    }


class CommEmailParser(object):
    """Utility to parse email replies."""
    address_prefix = comm.REPLY_TO_PREFIX

    def __init__(self, email_text):
        """Decode base64 email and turn it into a Django email object."""
        try:
            log.info('CommEmailParser received email: ' + email_text)
            email_text = base64.standard_b64decode(
                urllib2.unquote(email_text.rstrip()))
        except TypeError:
            # Corrupt or invalid base 64.
            self.decode_error = True
            log.info('Decoding error for CommEmailParser')
            return

        self.email = message_from_string(email_text)

        payload = self.email.get_payload()  # If not multipart, it's a string.
        if isinstance(payload, list):
            # If multipart, get the plaintext part.
            for part in payload:
                if part.get_content_type() == 'text/plain':
                    payload = part.get_payload()
                    break

        self.reply_text = EmailReplyParser.read(payload).reply

    def _get_address_line(self):
        return parseaddr(self.email['to'])

    def get_uuid(self):
        name, addr = self._get_address_line()

        if addr.startswith(self.address_prefix):
            # Strip everything between "reply+" and the "@" sign.
            uuid = addr[len(self.address_prefix):].split('@')[0]
        else:
            log.info('TO: address missing or not related to comm. (%s)'
                      % unicode(self.email).strip())
            return False

        return uuid

    def get_body(self):
        return self.reply_text


def save_from_email_reply(reply_text):
    from mkt.comm.utils import create_comm_note

    log.debug("Saving from email reply")

    parser = CommEmailParser(reply_text)
    if hasattr(parser, 'decode_error'):
        return False

    uuid = parser.get_uuid()

    if not uuid:
        return False
    try:
        tok = CommunicationThreadToken.objects.get(uuid=uuid)
    except CommunicationThreadToken.DoesNotExist:
        log.error('An email was skipped with non-existing uuid %s.' % uuid)
        return False

    if user_has_perm_thread(tok.thread, tok.user) and tok.is_valid():
        # Deduce an appropriate note type.
        note_type = comm.NO_ACTION
        if (tok.user.addonuser_set.filter(addon=tok.thread.addon).exists()):
            note_type = comm.DEVELOPER_COMMENT
        elif acl.action_allowed_user(tok.user, 'Apps', 'Review'):
            note_type = comm.REVIEWER_COMMENT

        t, note = create_comm_note(tok.thread.addon, tok.thread.version,
                                   tok.user, parser.get_body(),
                                   note_type=note_type)
        log.info('A new note has been created (from %s using tokenid %s).'
                 % (tok.user.id, uuid))
        return note
    elif tok.is_valid():
        log.error('%s did not have perms to reply to comm email thread %s.'
                  % (tok.user.email, tok.thread.id))
    else:
        log.error('%s tried to use an invalid comm token for thread %s.'
                  % (tok.user.email, tok.thread.id))

    return False


def get_reply_token(thread, user_id):
    tok, created = CommunicationThreadToken.objects.get_or_create(
        thread=thread, user_id=user_id)

    # We expire a token after it has been used for a maximum number of times.
    # This is usually to prevent overusing a single token to spam to threads.
    # Since we're re-using tokens, we need to make sure they are valid for
    # replying to new notes so we reset their `use_count`.
    if not created:
        tok.update(use_count=0)
    else:
        log.info('Created token with UUID %s for user_id: %s.' %
                 (tok.uuid, user_id))
    return tok
