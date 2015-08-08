import hashlib
import os
from datetime import datetime

from django.conf import settings
from django.core.cache import cache
from django.core.files.storage import default_storage as storage

import commonware.log
import cronjobs

from mkt.files.models import FileValidation
from mkt.site.storage_utils import storage_is_remote, walk_storage


log = commonware.log.getLogger('z.cron')


@cronjobs.register
def cleanup_extracted_file():
    log.info('Removing extracted files for file viewer.')
    root = os.path.join(settings.TMP_PATH, 'file_viewer')
    # Local storage uses local time for file modification. S3 uses UTC time.
    now = datetime.utcnow if storage_is_remote() else datetime.now
    for path in storage.listdir(root)[0]:
        full = os.path.join(root, path)
        age = now() - storage.modified_time(os.path.join(full,
                                                         'manifest.webapp'))
        if age.total_seconds() > (60 * 60):
            log.debug('Removing extracted files: %s, %dsecs old.' %
                      (full, age.total_seconds()))
            for subroot, dirs, files in walk_storage(full):
                for f in files:
                    storage.delete(os.path.join(subroot, f))
            # Nuke out the file and diff caches when the file gets removed.
            id = os.path.basename(path)
            try:
                int(id)
            except ValueError:
                continue

            key = hashlib.md5()
            key.update(str(id))
            cache.delete('%s:memoize:%s:%s' % (settings.CACHE_PREFIX,
                                               'file-viewer', key.hexdigest()))


@cronjobs.register
def cleanup_validation_results():
    """Will remove all validation results.  Used when the validator is
    upgraded and results may no longer be relevant."""
    # With a large enough number of objects not using tracebacks
    all = FileValidation.objects.all()
    log.info('Removing %s old validation results.' % (all.count()))
    all.delete()
