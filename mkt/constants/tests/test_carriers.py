from mpconstants.carriers import CARRIER_DETAILS
from nose.tools import eq_, ok_

import mkt.constants.carriers as carriers
from mkt.site.tests import TestCase


class TestCarriers(TestCase):
    def test_no_missing_carrier(self):
        defined_carriers = carriers.CARRIER_SLUGS
        available_carriers = {c['slug'] for c in CARRIER_DETAILS.values()}
        eq_(list(available_carriers.difference(defined_carriers)), [])

    def test_carrier_map(self):
        # Dummy check, make sure at least carrierless exists.
        eq_(carriers.CARRIER_MAP['carrierless'], carriers.UNKNOWN_CARRIER)

        for carrier in carriers.CARRIER_MAP.values():
            # Make sure the carrier map contains carrier objects.
            ok_(issubclass(carrier, carriers.CARRIER))

            # Make sure we can find each carrier in the carrier module locals.
            eq_(getattr(carriers, carrier.__name__), carrier)

    def test_carriers_no_duplicate(self):
        eq_(len(carriers.CARRIER_IDS), len(carriers.CARRIER_SLUGS))
