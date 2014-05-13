import logging

from django.shortcuts import render

from pyelasticsearch.exceptions import ElasticHttpError


log = logging.getLogger('z.es')


class ElasticsearchExceptionMiddleware(object):

    def process_exception(self, request, exception):
        if (issubclass(exception.__class__, ElasticHttpError)):
            log.error(u'Elasticsearch error: %s' % exception)
            return render(request, 'search/down.html', status=503)
