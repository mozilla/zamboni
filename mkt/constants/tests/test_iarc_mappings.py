from nose.tools import ok_

import mkt.site.tests

from mkt.constants.iarc_mappings import (
    HUMAN_READABLE_DESCS_AND_INTERACTIVES, REVERSE_DESCS, REVERSE_DESCS_V2,
    REVERSE_INTERACTIVES, REVERSE_INTERACTIVES_V2)


class TestIARCMappings(mkt.site.tests.TestCase):

    def test_all_human_readable_strings_are_present(self):
        for key in REVERSE_DESCS:
            ok_(key in HUMAN_READABLE_DESCS_AND_INTERACTIVES)
        for key in REVERSE_DESCS_V2:
            ok_(key in HUMAN_READABLE_DESCS_AND_INTERACTIVES)
        for key in REVERSE_INTERACTIVES:
            ok_(key in HUMAN_READABLE_DESCS_AND_INTERACTIVES)
        for key in REVERSE_INTERACTIVES_V2:
            ok_(key in HUMAN_READABLE_DESCS_AND_INTERACTIVES)
        for value in HUMAN_READABLE_DESCS_AND_INTERACTIVES.values():
            ok_(value)
