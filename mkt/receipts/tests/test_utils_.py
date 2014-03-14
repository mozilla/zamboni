from nose.tools import eq_
from receipts.receipts import Receipt

from amo.tests import TestCase
from mkt.receipts.tests.test_verify import sample
from mkt.receipts.utils import reissue_receipt


class TestReissue(TestCase):

    def test_expired(self):
        old = Receipt(sample).receipt_decoded()
        new = Receipt(reissue_receipt(sample)).receipt_decoded()
        for greater in ['exp', 'iat', 'nbf']:
            assert new[greater] > old[greater], (
                '{0} for new: {1} should be greater than old: {2}'.format(
                    greater, new[greater], old[greater]))

        for same in ['product', 'detail', 'iss', 'reissue', 'typ', 'user',
                     'verify']:
            eq_(new[same], old[same], (
                '{0} for new: {1} should be the same as old: {2}'.format(
                    greater, new[same], old[same])))
