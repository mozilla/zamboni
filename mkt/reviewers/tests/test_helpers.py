# -*- coding: utf-8 -*-
from nose.tools import eq_

import mkt
import mkt.site.tests
from mkt.site.utils import app_factory, version_factory
from mkt.reviewers import helpers


class TestGetPosition(mkt.site.tests.TestCase):

    def setUp(self):
        # Add a public, reviewed app for measure. It took 4 days for this app
        # to get reviewed.
        self.public_app = app_factory(
            version_kw={'created': self.days_ago(7),
                        'nomination': self.days_ago(7),
                        'reviewed': self.days_ago(3)})

        # Took 8 days for another public app to get reviewed.
        app_factory(
            version_kw={'nomination': self.days_ago(10),
                        'reviewed': self.days_ago(2)})

        # Add to the queue 2 pending apps for good measure.
        app_factory(
            status=mkt.STATUS_PENDING,
            file_kw={'status': mkt.STATUS_PENDING},
            version_kw={'nomination': self.days_ago(3)})

        app_factory(
            status=mkt.STATUS_PENDING,
            file_kw={'status': mkt.STATUS_PENDING},
            version_kw={'nomination': self.days_ago(1)})

        # A deleted app that shouldn't change calculations.
        app_factory(
            status=mkt.STATUS_DELETED,
            file_kw={'status': mkt.STATUS_PENDING},
            version_kw={'nomination': self.days_ago(1)})

    def test_min(self):
        pending_app = app_factory(
            status=mkt.STATUS_PENDING,
            file_kw={'status': mkt.STATUS_PENDING},
            version_kw={'nomination': self.days_ago(42)})
        pos = helpers.get_position(pending_app)
        eq_(pos['days'], 1)

    def test_packaged_app(self):
        self.public_app.update(is_packaged=True)
        version = version_factory(
            addon=self.public_app, file_kw={'status': mkt.STATUS_PENDING})
        self.public_app.reload()
        eq_(self.public_app.latest_version, version)
        self._test_position(self.public_app)

    def test_pending_app(self):
        pending_app = app_factory(
            status=mkt.STATUS_PENDING,
            file_kw={'status': mkt.STATUS_PENDING})
        self._test_position(pending_app)

    def _test_position(self, app):
        app.latest_version.update(nomination=self.days_ago(2))
        pos = helpers.get_position(app)

        # We set the nomination to 2 days ago.
        eq_(pos['days_in_queue'], 2)

        # There are three pending apps.
        eq_(pos['total'], 3)

        # It took 12 days for 2 apps to get reviewed, giving us an average of
        # 6 days to go from pending->public, but we've already waited 2 days.
        eq_(pos['days'], 4)

        # There is one pending app in front of us.
        eq_(pos['pos'], 2)
