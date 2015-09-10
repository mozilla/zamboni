from django import http
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied

from mock import Mock, patch

import mkt.site.tests
from mkt.access import acl
from mkt.files.decorators import allowed


class AllowedTest(mkt.site.tests.TestCase):

    def setUp(self):
        self.request = Mock()
        self.file = Mock()

    @patch.object(acl, 'check_reviewer', lambda x: True)
    def test_reviewer_allowed(self):
        self.assertTrue(allowed(self.request, self.file))

    @patch.object(acl, 'check_reviewer', lambda x: False)
    def test_reviewer_unallowed(self):
        self.assertRaises(PermissionDenied, allowed, self.request, self.file)

    @patch.object(acl, 'check_reviewer', lambda x: False)
    def test_addon_not_found(self):
        class MockVersion():
            @property
            def addon(self):
                raise ObjectDoesNotExist
        self.file.version = MockVersion()
        self.assertRaises(http.Http404, allowed, self.request, self.file)
