import mkt
import mkt.site.tests

import mkt.constants.comm as comm


class TestCommConstants(mkt.site.tests.TestCase):

    def setUp(self):
        # TODO (hi mat): remove these from mkt/site/log.py.
        self.blocked = [
            mkt.LOG.RETAIN_VERSION.id,
            mkt.LOG.REQUEST_VERSION.id,
            mkt.LOG.PRELIMINARY_VERSION.id,
            mkt.LOG.REQUEST_SUPER_REVIEW.id
        ]

    def test_review_queue_covered(self):
        """
        Test that every review queue log has its own note type.

        If this test is failing, tell ngoke to add a new note type.
        """
        for log_type in mkt.LOG_REVIEW_QUEUE:
            if log_type in self.blocked:
                continue

            assert comm.ACTION_MAP(log_type) != comm.NO_ACTION, log_type
            assert comm.ACTION_MAP(log_type) in comm.NOTE_TYPES, log_type
