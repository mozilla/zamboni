from django.test.client import RequestFactory

import elasticsearch
import mock
from nose.tools import eq_

import mkt.site.tests
from mkt.search.middleware import ElasticsearchExceptionMiddleware as ESM


class TestElasticsearchExceptionMiddleware(mkt.site.tests.TestCase):

    def setUp(self):
        self.request = RequestFactory()

    @mock.patch('mkt.search.middleware.render')
    def test_exceptions_we_catch(self, render_mock):
        # These are instantiated with an error string.
        for e in [elasticsearch.ElasticsearchException,
                  elasticsearch.SerializationError,
                  elasticsearch.TransportError,
                  elasticsearch.NotFoundError,
                  elasticsearch.RequestError]:
            ESM().process_exception(self.request, e(503, 'ES ERROR'))
            render_mock.assert_called_with(self.request, 'search/down.html',
                                           status=503)
            render_mock.reset_mock()

    @mock.patch('mkt.search.middleware.render')
    def test_exceptions_we_do_not_catch(self, render_mock):
        ESM().process_exception(self.request, Exception)
        eq_(render_mock.called, False)
