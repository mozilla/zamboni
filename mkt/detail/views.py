from django import http
from django.views.decorators.http import etag

import commonware.log

import mkt
from mkt.constants import MANIFEST_CONTENT_TYPE
from mkt.site.decorators import allow_cross_site_request
from mkt.webapps.models import Webapp


log = commonware.log.getLogger('z.detail')


@allow_cross_site_request
def manifest(request, uuid):
    """Returns the "mini" manifest for packaged apps.

    If not a packaged app, returns a 404.

    """
    try:
        addon = (Webapp.objects.all().only_translations()
                 .get(disabled_by_user=False, is_packaged=True, guid=uuid))
    except Webapp.DoesNotExist:
        raise http.Http404

    is_available = addon.status in [mkt.STATUS_PUBLIC, mkt.STATUS_UNLISTED,
                                    mkt.STATUS_BLOCKED]
    if is_available:
        # If the package is available to anonymous users, we don't care about
        # this and can save the query time.
        is_owner = is_available_to_owner = False
    else:
        is_owner = addon.authors.filter(pk=request.user.pk).exists()
        is_available_to_owner = addon.status == mkt.STATUS_APPROVED

    if (is_available or (is_available_to_owner and is_owner)):

        manifest_content, manifest_etag = addon.get_cached_manifest()

        @etag(lambda r, a: manifest_etag)
        def _inner_view(request, addon):
            response = http.HttpResponse(manifest_content,
                                         content_type=MANIFEST_CONTENT_TYPE)
            return response

        return _inner_view(request, addon)

    else:
        raise http.Http404
