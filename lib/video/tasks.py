import datetime
import logging

from django.conf import settings

import waffle

import mkt
from lib.post_request_task.task import task as post_request_task
from lib.video import library
from mkt.site.storage_utils import (copy_stored_file, local_storage,
                                    private_storage, public_storage)
from mkt.users.models import UserProfile
from mkt.webapps.models import Preview


log = logging.getLogger('z.devhub.task')
time_limits = settings.CELERY_TIME_LIMITS['lib.video.tasks.resize_video']


# Video decoding can take a while, so let's increase these limits.
@post_request_task(time_limit=time_limits['hard'],
                   soft_time_limit=time_limits['soft'])
def resize_video(src, pk, user_pk=None, **kw):
    """Try and resize a video and cope if it fails."""
    instance = Preview.objects.get(pk=pk)
    user = UserProfile.objects.get(pk=user_pk) if user_pk else None
    try:
        copy_stored_file(src, src, src_storage=private_storage,
                         dst_storage=local_storage)
        result = _resize_video(src, instance, **kw)
    except Exception, err:
        log.error('Error on processing video: %s' % err)
        _resize_error(src, instance, user)
        raise

    if not result:
        log.error('Error on processing video, _resize_video not True.')
        _resize_error(src, instance, user)

    log.info('Video resize complete.')

    # Updated modified stamp on the addon.
    instance.update(modified=datetime.datetime.now())


def _resize_error(src, instance, user):
    """An error occurred in processing the video, deal with that approp."""
    mkt.log(mkt.LOG.VIDEO_ERROR, instance, user=user)
    instance.delete()


def _resize_video(src, instance, lib=None, **kw):
    """
    Given a preview object and a file somewhere: encode into the full
    preview size and generate a thumbnail.
    """
    log.info('[1@None] Encoding video %s' % instance.pk)
    lib = lib or library
    if not lib:
        log.info('Video library not available for %s' % instance.pk)
        return

    video = lib(src)
    video.get_meta()
    if not video.is_valid():
        log.info('Video is not valid for %s' % instance.pk)
        return

    if waffle.switch_is_active('video-encode'):
        # Do the video encoding.
        try:
            video_file = video.get_encoded(mkt.ADDON_PREVIEW_SIZES[1])
        except Exception:
            log.info('Error encoding video for %s, %s' %
                     (instance.pk, video.meta), exc_info=True)
            return

    # Do the thumbnail next, this will be the signal that the
    # encoding has finished.
    try:
        thumbnail_file = video.get_screenshot(mkt.ADDON_PREVIEW_SIZES[0])
    except Exception:
        # We'll have this file floating around because the video
        # encoded successfully, or something has gone wrong in which case
        # we don't want the file around anyway.
        if waffle.switch_is_active('video-encode'):
            local_storage.delete(video_file)
        log.info('Error making thumbnail for %s' % instance.pk, exc_info=True)
        return

    copy_stored_file(thumbnail_file, instance.thumbnail_path,
                     src_storage=local_storage, dst_storage=public_storage)
    if waffle.switch_is_active('video-encode'):
        # Move the file over, removing the temp file.
        copy_stored_file(video_file, instance.image_path,
                         src_storage=local_storage,
                         dst_storage=public_storage)
    else:
        # We didn't re-encode the file.
        copy_stored_file(src, instance.image_path, src_storage=local_storage,
                         dst_storage=public_storage)
        #
    # Now remove local files.
    local_storage.delete(thumbnail_file)
    if waffle.switch_is_active('video-encode'):
        local_storage.delete(video_file)

    # Ensure everyone has read permission on the file.
    instance.sizes = {'thumbnail': mkt.ADDON_PREVIEW_SIZES[0],
                      'image': mkt.ADDON_PREVIEW_SIZES[1]}
    instance.save()
    log.info('Completed encoding video: %s' % instance.pk)
    return True
