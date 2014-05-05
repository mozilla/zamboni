from django.conf import settings
from django.db.models import Q
from django.shortcuts import render

import elasticutils

import amo
from amo.utils import chunked
from zadmin.decorators import admin_required

from mkt.webapps.models import Webapp
from mkt.webapps.tasks import update_manifests


@admin_required(reviewers=True)
def manifest_revalidation(request):
    if request.method == 'POST':
        # Collect the apps to revalidate.
        qs = Q(is_packaged=False, status=amo.STATUS_PUBLIC,
               disabled_by_user=False)
        webapp_pks = Webapp.objects.filter(qs).values_list('pk', flat=True)

        for pks in chunked(webapp_pks, 100):
            update_manifests.delay(list(pks), check_hash=False)

        amo.messages.success(request, 'Manifest revalidation queued')

    return render(request, 'zadmin/manifest.html')


@admin_required
def elastic(request):
    es = elasticutils.get_es()

    indexes = set(settings.ES_INDEXES.values())
    es_mappings = es.get_mapping(None, indexes)
    ctx = {
        'aliases': es.aliases(),
        'health': es.health(),
        'state': es.cluster_state(),
        'mappings': [(index, es_mappings.get(index, {})) for index in indexes],
    }
    return render(request, 'zadmin/elastic.html', ctx)
