"""Tests for the activitylog."""
from datetime import datetime

from nose.tools import eq_

import mkt
import mkt.site.tests
from mkt.webapps.models import Webapp
from mkt.users.models import UserProfile


class LogTest(mkt.site.tests.TestCase):
    def setUp(self):
        u = UserProfile.objects.create(username='foo')
        mkt.set_user(u)

    def test_details(self):
        """
        If we get details, verify they are stored as JSON, and we get out what
        we put in.
        """
        a = Webapp.objects.create(name='kumar is awesome')
        magic = dict(title='no', body='way!')
        al = mkt.log(mkt.LOG.DELETE_REVIEW, 1, a, details=magic)

        eq_(al.details, magic)
        eq_(al._details, '{"body": "way!", "title": "no"}')

    def test_created(self):
        """
        Verify that we preserve the create date.
        """
        al = mkt.log(mkt.LOG.CUSTOM_TEXT, 'hi', created=datetime(2009, 1, 1))

        eq_(al.created, datetime(2009, 1, 1))
