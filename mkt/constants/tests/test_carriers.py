from nose.tools import eq_

from mkt.constants.carriers import CARRIER_IDS, CARRIER_SLUGS


def test_carriers_no_duplicate():
    eq_(len(CARRIER_IDS), len(CARRIER_SLUGS))
