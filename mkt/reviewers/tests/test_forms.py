from datetime import date

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile

from mock import patch
from nose.tools import eq_

import mkt
from mkt.comm.forms import CommAttachmentForm
from mkt.reviewers.forms import ModerateLogForm
from mkt.site.tests import TestCase


@patch.object(settings, 'MAX_REVIEW_ATTACHMENT_UPLOAD_SIZE', 1024)
class TestReviewAppAttachmentForm(TestCase):

    def setUp(self):
        self.max_size = settings.MAX_REVIEW_ATTACHMENT_UPLOAD_SIZE

    def post_data(self, **kwargs):
        post_data = {
            'description': 'My Test File'
        }
        post_data.update(kwargs)
        return post_data

    def file_data(self, size=1024):
        file_data = {
            'attachment': None
        }
        if size:
            file_data['attachment'] = SimpleUploadedFile('bacon.txt',
                                                         ' ' * size)
        return file_data

    def test_no_attachment(self):
        file_data = self.file_data(size=0)
        self.check_valid(False, file_data=file_data)

    def test_no_description(self):
        post_data = self.post_data(description=None)
        self.check_valid(True, post_data=post_data)

    def test_attachment_okay(self):
        file_data = self.file_data(size=self.max_size)
        self.check_valid(True, file_data=file_data)

    def test_attachment_too_large(self):
        file_data = self.file_data(size=self.max_size + 1)
        self.check_valid(False, file_data=file_data)

    def check_valid(self, valid, post_data=None, file_data=None):
        if not post_data:
            post_data = self.post_data()
        if not file_data:
            file_data = self.file_data()
        form = CommAttachmentForm(post_data, file_data)
        eq_(form.is_valid(), valid)


class TestModerationLogForm(TestCase):

    def test_clean(self):
        post_data = {
            'start': '2014-12-01',
            'end': '2015-01-01',
            'search': 'approved',
        }
        form = ModerateLogForm(post_data)
        assert form.is_valid()
        eq_(form.cleaned_data['start'], date(2014, 12, 01))
        # End date should a day ahead.
        eq_(form.cleaned_data['end'], date(2015, 01, 02))
        eq_(form.cleaned_data['search'], mkt.LOG.APPROVE_REVIEW)
