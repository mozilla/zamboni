from tower import ugettext_lazy as _lazy

from constants.applications import (DEVICE_DESKTOP, DEVICE_GAIA, DEVICE_MOBILE,
                                    DEVICE_TABLET)


class FORM_DESKTOP(object):
    id = 1
    name = _lazy(u'Desktop')
    slug = 'desktop'


class FORM_MOBILE(object):
    id = 2
    name = _lazy(u'Mobile')
    slug = 'mobile'


class FORM_TABLET(object):
    id = 3
    name = _lazy(u'Tablet')
    slug = 'tablet'


FORM_FACTORS = [FORM_DESKTOP, FORM_MOBILE, FORM_TABLET]
FORM_FACTOR_CHOICES = dict((f.id, f) for f in FORM_FACTORS)
FORM_FACTOR_LOOKUP = dict((f.slug, f) for f in FORM_FACTORS)


# Mapping from old device types to form_factors. Used as a compatibility layer
# to avoid breaking the API.
DEVICE_TO_FORM_FACTOR = {
    DEVICE_DESKTOP.id: FORM_DESKTOP,
    DEVICE_MOBILE.id: FORM_MOBILE,
    DEVICE_TABLET.id: FORM_TABLET,
    DEVICE_GAIA.id: FORM_MOBILE,
}
