import json

import path

import amo
import amo.tests
from files.models import FileUpload


# TODO: Leave this here until unused in AMO. Update everything under mkt/ to
# use the `UploadTest` from mkt/files/tests/test_models.py.
class UploadTest(amo.tests.TestCase, amo.tests.AMOPaths):
    """
    Base for tests that mess with file uploads, safely using temp directories.
    """
    fixtures = ['applications/all_apps.json', 'base/appversion']

    def setUp(self):
        self._rename = path.path.rename
        path.path.rename = path.path.copy
        # The validator task (post Addon upload) loads apps.json
        # so ensure it exists:
        from django.core.management import call_command
        call_command('dump_apps')

    def tearDown(self):
        path.path.rename = self._rename

    def file_path(self, *args, **kw):
        return self.file_fixture_path(*args, **kw)

    def get_upload(self, filename=None, abspath=None, validation=None,
                   is_webapp=False):
        xpi = open(abspath if abspath else self.file_path(filename)).read()
        upload = FileUpload.from_post([xpi], filename=abspath or filename,
                                      size=1234)
        # Simulate what fetch_manifest() does after uploading an app.
        upload.is_webapp = is_webapp
        upload.validation = (validation or
                             json.dumps(dict(errors=0, warnings=1, notices=2,
                                             metadata={}, messages=[])))
        upload.save()
        return upload
