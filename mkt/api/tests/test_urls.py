from mock import patch
from nose.tools import eq_, ok_

from django.core.urlresolvers import resolve, Resolver404

import mkt.site.tests
from mkt.api.urls import include_version


# Semantic names for the relevant values in the tuple returned by include().
MODULE, NAMESPACE = 0, 2

# Semantic names for the relevant values in the tuple returned by resolve().
FUNCTION = 0


class TestIncludeVersion(mkt.site.tests.TestCase):
    def includes(self):
        return include_version(1), include_version(2)

    @patch('django.conf.settings.API_CURRENT_VERSION', 1)
    def test_v1(self):
        v1, v2 = self.includes()

        eq_(v1[NAMESPACE], None)
        eq_(v2[NAMESPACE], 'api-v2')

        ok_('v1' in v1[MODULE].__file__)
        ok_('v2' in v2[MODULE].__file__)

    @patch('django.conf.settings.API_CURRENT_VERSION', 2)
    def test_v2(self):
        v1, v2 = self.includes()

        eq_(v1[NAMESPACE], 'api-v1')
        eq_(v2[NAMESPACE], None)

        ok_('v1' in v1[MODULE].__file__)
        ok_('v2' in v2[MODULE].__file__)


class BaseTestAPIVersionURLs(object):
    """
    Mixin for API version URL tests providing helpful assertions for common
    testing scenarios.
    """

    def assertViewName(self, url, view_name):
        """
        Assert that a resolution of the passed URL is for the view with the
        passed name.
        """
        resolved = resolve(url)
        eq_(resolved[FUNCTION].func_name, view_name)

    def assertView404(self, url):
        """
        Assert that a resolution of the passed URL does one of the following
        two things, each of which indicate a 404:

        1) Raises a Resolver404 error.
        2) Resolves to a view with the name 'EndpointRemoved'.
        """
        try:
            resolved = resolve(url)
        except Resolver404:
            pass
        else:
            eq_(resolved[FUNCTION].func_name, 'EndpointRemoved')


class TestAPIv1URLs(BaseTestAPIVersionURLs, mkt.site.tests.TestCase):
    """
    Tests for expected changes of URLs between versions of the API using the v1
    urlconf.
    """
    urls = 'mkt.api.v1.urls'

    def test_collections(self):
        """
        Tests the v1 endpoints removed in v2 still work with v1.
        """
        self.assertViewName('/apps/search/featured/', 'FeaturedSearchView')


class TestAPIv2URLs(BaseTestAPIVersionURLs, mkt.site.tests.TestCase):
    """
    Tests for expected changes of URLs between versions of the API using the v2
    urlconf.
    """
    urls = 'mkt.api.v2.urls'

    def test_collections(self):
        """
        Tests the v2 endpoints removal.
        """
        self.assertView404('/apps/search/featured/')
