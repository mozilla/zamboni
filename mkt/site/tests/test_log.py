"""Tests for the activitylog."""
from datetime import datetime

from nose.tools import eq_

import mkt
from mkt.site.tests import TestCase, user_factory
from mkt.webapps.models import Webapp


class LogTest(TestCase):
    def setUp(self):
        mkt.set_user(user_factory())

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
