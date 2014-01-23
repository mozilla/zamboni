from nose.tools import ok_
from test_utils import RequestFactory

from django.http import Http404

import amo.tests
from mkt.api.views import endpoint_removed


class TestEndpointRemoved(amo.tests.TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_exempt(self):
        ok_(endpoint_removed.csrf_exempt)

    def test_404(self):
        methods = ['get', 'post', 'options']
        for method in methods:
            request = getattr(self.factory, method)('/')
            with self.assertRaises(Http404):
                endpoint_removed(request)
