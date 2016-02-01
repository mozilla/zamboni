import logging

import elasticsearch

from mkt.site.utils import render

log = logging.getLogger('z.elasticsearch')


class ElasticsearchExceptionMiddleware(object):

    def process_exception(self, request, exception):
        if (issubclass(exception.__class__,
                       elasticsearch.ElasticsearchException)):
            log.error(u'Elasticsearch error: %s' % exception)
            return render(request, 'search/down.html', status=503)
