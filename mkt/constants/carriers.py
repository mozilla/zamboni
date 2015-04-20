# -*- coding: utf-8 -*-
from mpconstants.carriers import CARRIER_DETAILS


class CARRIER(object):
    pass


for k, carrier in CARRIER_DETAILS.items():
    # Create a CARRIER objects for each carrier and add it to locals so that we
    # can import them from this module.
    locals()[k] = type(k, (CARRIER,), carrier)

CARRIER_MAP = dict((c.slug, c) for name, c in locals().items() if
                   type(c) is type and c != CARRIER and issubclass(c, CARRIER))
CARRIERS = CARRIER_MAP.values()

CARRIER_IDS = frozenset([c.id for c in CARRIERS])
CARRIER_SLUGS = frozenset([c.slug for c in CARRIERS])
CARRIER_CHOICES = [(c.id, c) for c in CARRIERS]
CARRIER_CHOICE_DICT = dict(CARRIER_CHOICES)
