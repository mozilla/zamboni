"""
A Marketplace only command that finds apps missing from the search index and
adds them.
"""
import sys

import elasticsearch

from django.core.management.base import BaseCommand

from mkt.webapps.indexers import WebappIndexer
from mkt.webapps.models import Webapp


class Command(BaseCommand):
    help = 'Fix up Marketplace index.'

    def handle(self, *args, **kwargs):
        index = WebappIndexer.get_index()
        doctype = WebappIndexer.get_mapping_type_name()
        es = WebappIndexer.get_es()

        app_ids = Webapp.objects.values_list('id', flat=True)

        missing_ids = []

        for app_id in app_ids:
            try:
                es.get(index, app_id, doctype, fields='id')
            except elasticsearch.NotFoundError:
                # App doesn't exist in our index, add it to `missing_ids`.
                missing_ids.append(app_id)

        if missing_ids:
            sys.stdout.write('Adding %s doc(s) to the index.'
                             % len(missing_ids))
            WebappIndexer().run_indexing(missing_ids, es)
        else:
            sys.stdout.write('No docs missing from index.')
