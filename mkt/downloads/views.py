from django import http
from django.db.transaction import non_atomic_requests
from django.shortcuts import get_object_or_404

import commonware.log

import mkt
from mkt.access import acl
from mkt.files.models import File
from mkt.site.decorators import allow_cross_site_request
from mkt.site.utils import HttpResponseSendFile
from mkt.webapps.models import Webapp


log = commonware.log.getLogger('z.downloads')


@non_atomic_requests  # This view should not do any writes to the db.
@allow_cross_site_request
def download_file(request, file_id, type=None):
    # Fetch what we need with a minimum amount of queries (Transforms on
    # Version and Webapp are avoided). This breaks several things like
    # translations, but it should be fine here, we don't need much to go on.
    file_ = get_object_or_404(File.objects.select_related('version'),
                              pk=file_id)
    webapp = get_object_or_404(Webapp.objects.all().no_transforms(),
                               pk=file_.version.addon_id, is_packaged=True)

    if webapp.is_disabled or file_.status == mkt.STATUS_DISABLED:
        if not acl.check_addon_ownership(request, webapp, viewer=True,
                                         ignore_disabled=True):
            raise http.Http404()

    # We treat blocked files like public files so users get the update.
    if file_.status in [mkt.STATUS_PUBLIC, mkt.STATUS_BLOCKED]:
        path = file_.signed_file_path

    else:
        # This is someone asking for an unsigned packaged app.
        if not acl.check_addon_ownership(request, webapp, dev=True):
            raise http.Http404()

        path = file_.file_path

    log.info('Downloading package: %s from %s' % (webapp.id, path))
    return HttpResponseSendFile(request, path, content_type='application/zip',
                                etag=file_.hash.split(':')[-1])
