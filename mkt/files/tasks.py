import logging

from django.conf import settings
from django.utils.translation import ugettext as _

from cache_nuggets.lib import Message
from post_request_task.task import task

from mkt.files.helpers import FileViewer
from mkt.files.models import File


task_log = logging.getLogger('z.task')


@task
def extract_file(file_id, **kw):
    # This message is for end users so they'll see a nice error.
    viewer = FileViewer(File.objects.get(pk=file_id))
    msg = Message('file-viewer:%s' % viewer)
    msg.delete()
    # This flag is so that we can signal when the extraction is completed.
    flag = Message(viewer._extraction_cache_key())
    task_log.debug('[1@%s] Unzipping %s for file viewer.' % (
        extract_file.rate_limit, viewer))

    try:
        flag.save('extracting')  # Set the flag to a truthy value.
        viewer.extract()
    except Exception, err:
        if settings.DEBUG:
            msg.save(_('There was an error accessing file %s. %s.')
                     % (viewer, err))
        else:
            msg.save(_('There was an error accessing file %s.') % viewer)
        task_log.error('[1@%s] Error unzipping: %s' % (extract_file.rate_limit,
                                                       err))
    finally:
        # Always delete the flag so the file never gets into a bad state.
        flag.delete()
