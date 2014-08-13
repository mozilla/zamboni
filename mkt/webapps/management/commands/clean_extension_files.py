import gc
import os

from django.conf import settings
from django.core.management.base import BaseCommand

import amo
from mkt.webapps.models import Addon


# Gratuitously stolen from
# http://www.mellowmorning.com/2010/03/03/django-query-set-iterator-for-really-large-querysets/
def queryset_iterator(queryset, chunksize=1000):
    '''
    Iterate over a Django Queryset ordered by the primary key

    This method loads a maximum of chunksize (default: 1000) rows in it's
    memory at the same time while django normally would load all rows in it's
    memory. Using the iterator() method only causes it to not preload all the
    classes.

    Note that the implementation of the iterator does not support ordered
    querysets.

    '''
    pk = 0
    last_pk = queryset.order_by('-pk')[0].pk
    queryset = queryset.order_by('pk')
    while pk < last_pk:
        for row in queryset.filter(pk__gt=pk)[:chunksize]:
            pk = row.pk
            yield row
        gc.collect()


class Command(BaseCommand):
    help = 'Find and list commands to delete non-Webapp files.'

    def handle(self, *args, **options):
        # Get all non-Webapps
        qs = Addon.with_deleted.exclude(type=amo.ADDON_WEBAPP).no_transforms()

        for addon in queryset_iterator(qs, chunksize=250):

            print "### Removing files for addon id=%s (%s)" % (addon.pk,
                                                               addon.slug)

            # Icons.
            # Icons have a name like {id}-{size}.png. Multiple apps share the
            # same icon folder.
            print 'rm %s/%s-*' % (addon.get_icon_dir(), addon.pk)

            # Previews.
            for preview in addon.previews.all():
                print 'rm %s' % preview.thumbnail_path
                print 'rm %s' % preview.image_path

            # Remove the addon files themselves.
            #
            # If this is a persona theme this removes all files within the
            # directory. If it is an extension this removes the .xpi file(s).
            print 'rm -rf %s' % os.path.join(settings.ADDONS_PATH,
                                             str(addon.pk))

            # Similar to above but remove the guarded addons files.
            print 'rm -rf %s' % os.path.join(settings.GUARDED_ADDONS_PATH,
                                             str(addon.pk))
