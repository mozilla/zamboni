import os
import uuid
from datetime import datetime

from django.conf import settings
from django.core.files.storage import default_storage as storage
from django.template.defaultfilters import filesizeformat

from appvalidator.constants import PRERELEASE_PERMISSIONS
import commonware.log
from PIL import Image
from tower import ugettext as _

import mkt
from lib.video import library as video_library
from mkt.comm.utils import create_comm_note
from mkt.constants import APP_PREVIEW_MINIMUMS, comm
from mkt.reviewers.models import EscalationQueue
from mkt.site.utils import ImageCheck
from mkt.users.models import UserProfile


log = commonware.log.getLogger('z.devhub')


def uri_to_pk(uri):
    """
    Convert a resource URI to the primary key of the resource.
    """
    return uri.rstrip('/').split('/')[-1]


def check_upload(file_obj, upload_type, content_type):
    errors = []
    upload_hash = ''
    is_icon = upload_type == 'icon'
    is_preview = upload_type == 'preview'
    is_video = content_type in mkt.VIDEO_TYPES

    if not any([is_icon, is_preview, is_video]):
        raise ValueError('Unknown upload type.')

    # By pushing the type onto the instance hash, we can easily see what
    # to do with the file later.
    ext = content_type.replace('/', '-')
    upload_hash = '%s.%s' % (uuid.uuid4().hex, ext)
    loc = os.path.join(settings.TMP_PATH, upload_type, upload_hash)

    with storage.open(loc, 'wb') as fd:
        for chunk in file_obj:
            fd.write(chunk)

    # A flag to prevent us from attempting to open the image with PIL.
    do_not_open = False

    if is_video:
        if not video_library:
            errors.append(_('Video support not enabled.'))
        else:
            video = video_library(loc)
            video.get_meta()
            if not video.is_valid():
                errors.extend(video.errors)

    else:
        check = ImageCheck(file_obj)
        if (not check.is_image() or
                content_type not in mkt.IMG_TYPES):
            do_not_open = True
            if is_icon:
                errors.append(_('Icons must be either PNG or JPG.'))
            else:
                errors.append(_('Images must be either PNG or JPG.'))

        if check.is_animated():
            do_not_open = True
            if is_icon:
                errors.append(_('Icons cannot be animated.'))
            else:
                errors.append(_('Images cannot be animated.'))

    max_size = (settings.MAX_ICON_UPLOAD_SIZE if is_icon else
                settings.MAX_VIDEO_UPLOAD_SIZE if is_video else
                settings.MAX_IMAGE_UPLOAD_SIZE if is_preview else None)

    if max_size and file_obj.size > max_size:
        do_not_open = True
        if is_icon or is_video:
            errors.append(
                _('Please use files smaller than %s.') %
                filesizeformat(max_size))

    if (is_icon or is_preview) and not is_video and not do_not_open:
        file_obj.seek(0)
        try:
            im = Image.open(file_obj)
            im.verify()
        except IOError:
            if is_icon:
                errors.append(_('Icon could not be opened.'))
            elif is_preview:
                errors.append(_('Preview could not be opened.'))
        else:
            size_x, size_y = im.size
            if is_icon:
                # TODO: This should go away when we allow uploads for
                # individual icon sizes.
                if size_x < 128 or size_y < 128:
                    errors.append(_('Icons must be at least 128px by 128px.'))

                if size_x != size_y:
                    errors.append(_('Icons must be square.'))

            elif is_preview:
                if (size_x < APP_PREVIEW_MINIMUMS[0] or
                    size_y < APP_PREVIEW_MINIMUMS[1]) and (
                        size_x < APP_PREVIEW_MINIMUMS[1] or
                        size_y < APP_PREVIEW_MINIMUMS[0]):
                    errors.append(
                        # L10n: {0} and {1} are the height/width of the preview
                        # in px.
                        _('App previews must be at least {0}px by {1}px or '
                          '{1}px by {0}px.').format(*APP_PREVIEW_MINIMUMS))

    return errors, upload_hash


def escalate_app(app, version, user, msg, log_type):
    # Add to escalation queue
    EscalationQueue.objects.get_or_create(addon=app)

    # Create comm note
    create_comm_note(app, version, user, msg,
                     note_type=comm.ACTION_MAP(log_type))

    # Log action
    mkt.log(log_type, app, version, created=datetime.now(),
            details={'comments': msg})
    log.info(u'[app:%s] escalated - %s' % (app.name, msg))


def handle_vip(addon, version, user):
    escalate_app(
        addon, version, user, u'VIP app updated',
        mkt.LOG.ESCALATION_VIP_APP)


def escalate_prerelease_permissions(app, validation, version):
    """Escalate the app if it uses prerelease permissions."""
    # When there are no permissions `validation['permissions']` will be
    # `False` so we should default to an empty list if `get` is falsey.
    app_permissions = validation.get('permissions') or []
    if any(perm in PRERELEASE_PERMISSIONS for perm in app_permissions):
        nobody = UserProfile.objects.get(email=settings.NOBODY_EMAIL_ADDRESS)
        escalate_app(
            app, version, nobody, 'App uses prerelease permissions',
            mkt.LOG.ESCALATION_PRERELEASE_APP)


def prioritize_app(app, user):
    app.update(priority_review=True)
    msg = u'Priority Review Requested'
    # Create notes and log entries.
    create_comm_note(app, app.latest_version, user, msg,
                     note_type=comm.PRIORITY_REVIEW_REQUESTED)
    mkt.log(mkt.LOG.PRIORITY_REVIEW_REQUESTED, app, app.latest_version,
            created=datetime.now(), details={'comments': msg})
