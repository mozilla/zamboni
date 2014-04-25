import logging
import os

import django.core.mail
from django.conf import settings

import jingo
from cache_nuggets.lib import Message
from celeryutils import task
from tower import ugettext as _

from amo.utils import get_email_backend


task_log = logging.getLogger('z.task')
jp_log = logging.getLogger('z.jp.repack')


@task
def extract_file(viewer, **kw):
    # This message is for end users so they'll see a nice error.
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
            msg.save(_('There was an error accessing file %s. %s.') %
                     (viewer, err))
        else:
            msg.save(_('There was an error accessing file %s.') % viewer)
        task_log.error('[1@%s] Error unzipping: %s' %
                       (extract_file.rate_limit, err))
    finally:
        # Always delete the flag so the file never gets into a bad state.
        flag.delete()


# The version/file creation methods expect a files.FileUpload object.
class FakeUpload(object):

    def __init__(self, path, hash, validation):
        self.path = path
        self.name = os.path.basename(path)
        self.hash = hash
        self.validation = validation


class RedisLogHandler(logging.Handler):
    """Logging handler that sends jetpack messages to redis."""

    def __init__(self, logger, upgrader, file_data, level=logging.WARNING):
        self.logger = logger
        self.upgrader = upgrader
        self.file_data = file_data
        logging.Handler.__init__(self, level)

    def emit(self, record):
        self.file_data['status'] = 'failed'
        self.file_data['msg'] = record.msg
        if 'file' in self.file_data:
            self.upgrader.file(self.file_data['file'], self.file_data)
        self.logger.removeHandler(self)


def send_upgrade_email(addon, new_version, sdk_version):
    cxn = get_email_backend()
    subject = u'%s updated to SDK version %s' % (addon.name, sdk_version)
    from_ = settings.DEFAULT_FROM_EMAIL
    to = set(addon.authors.values_list('email', flat=True))
    t = jingo.env.get_template('files/jetpack_upgraded.txt')
    msg = t.render({'addon': addon, 'new_version': new_version,
                    'sdk_version': sdk_version})
    django.core.mail.send_mail(subject, msg, from_, to, connection=cxn)
