import os
from optparse import make_option

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage as storage

import mkt
from mkt.site.decorators import use_master
from mkt.site.storage_utils import walk_storage
from mkt.site.utils import chunked, resize_image
from mkt.webapps.models import Webapp


extensions = ['.png', '.jpg', '.gif']
sizes = mkt.CONTENT_ICON_SIZES
size_suffixes = ['-%s' % s for s in sizes]


@use_master
def convert(directory, delete=False):
    print 'Converting icons in %s' % directory

    pks = []
    k = 0
    for path, names, filenames in walk_storage(directory):
        for filename in filenames:
            old = os.path.join(path, filename)
            pre, ext = os.path.splitext(old)
            if (pre[-3:] in size_suffixes or ext not in extensions):
                continue

            if not storage.size(old):
                print 'Icon %s is empty, ignoring.' % old
                continue

            for size, size_suffix in zip(sizes, size_suffixes):
                new = '%s%s%s' % (pre, size_suffix, '.png')
                if os.path.exists(new):
                    continue
                resize_image(old, new, (size, size), remove_src=False)

            if ext != '.png':
                pks.append(os.path.basename(pre))

            if delete:
                storage.delete(old)

            k += 1
            if not k % 1000:
                print "... converted %s" % k

    for chunk in chunked(pks, 100):
        Webapp.objects.filter(pk__in=chunk).update(icon_type='image/png')


class Command(BaseCommand):
    help = 'Process icons to -32, -48, -64 and optionally delete'
    option_list = BaseCommand.option_list + (
        make_option('--delete', action='store_true',
                    dest='delete', help='Deletes the old icons.'),
    )

    def handle(self, *args, **options):
        start_dir = settings.ADDON_ICONS_PATH
        convert(start_dir, delete=options.get('delete'))
