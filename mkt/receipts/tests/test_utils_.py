import calendar
import time

from nose.tools import eq_

from receipts.receipts import Receipt
from amo.tests import TestCase
from mkt.receipts.utils import reissue_receipt, sign
from mkt.receipts.tests.utils import get_sample_app_receipt


class TestReissue(TestCase):

    def test_expired(self):
        receipt_data = get_sample_app_receipt()
        curr_time = calendar.timegm(time.gmtime())
        receipt_data['iat'] = curr_time - 1000
        receipt_data['nbf'] = curr_time - 1000
        receipt_data['exp'] = curr_time
        receipt = sign(receipt_data)
        old = Receipt(receipt).receipt_decoded()
        new = Receipt(reissue_receipt(receipt)).receipt_decoded()
        for greater in ['exp', 'iat', 'nbf']:
            assert new[greater] > old[greater], (
                '{0} for new: {1} should be greater than old: {2}'.format(
                    greater, new[greater], old[greater]))

        for same in ['product', 'detail', 'iss', 'reissue', 'typ', 'user',
                     'verify']:
            eq_(new[same], old[same], (
                '{0} for new: {1} should be the same as old: {2}'.format(
                    greater, new[same], old[same])))
