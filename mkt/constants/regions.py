import inspect
import sys

from tower import ugettext_lazy as _lazy

from mpconstants import countries

from mkt.constants import ratingsbodies
from mkt.constants.ratingsbodies import slugify_iarc_name


class REGION(object):
    """
    A region is like a country but more confusing.

    id::
        The primary key used to identify a region in the DB.

    name::
        The text that appears in the header and region selector menu.

    slug::
        The text that gets stored in the cookie or in ?region=<slug>.
        Use the ISO-3166 code please.

    mcc::
        Don't know what an ITU MCC is? They're useful for carrier billing.
        Read http://en.wikipedia.org/wiki/List_of_mobile_country_codes

    adolescent::
        With a mature region (meaning, it has a volume of useful data) we
        are able to calculate ratings and rankings independently. If a
        store is immature it will continue using the global popularity
        measure. If a store is mature it will use the smaller, more
        relevant set of data.

    weight::
        Determines sort order (after slug).

    special::
        Does this region need to be reviewed separately? That region is
        special.

    low_memory::
        Does this region have low-memory (Tarako) devices?

    """
    id = None
    name = slug = ''
    default_currency = 'USD'
    default_language = 'en-US'
    adolescent = True
    mcc = None
    weight = 0
    ratingsbody = None
    special = False
    low_memory = False


class RESTOFWORLD(REGION):
    id = 1
    name = _lazy(u'Rest of World')
    slug = 'restofworld'
    weight = -1


# These keys are from marketplace-constants
# See https://mana.mozilla.org/wiki/display/MARKET/How+to+add+a+new+region
lookup = {
    'ARG': _lazy(u'Argentina'),
    'BGD': _lazy(u'Bangladesh'),
    'BRA': _lazy(u'Brazil'),
    'CHL': _lazy(u'Chile'),
    'CHN': _lazy(u'China'),
    'COL': _lazy(u'Colombia'),
    'CRI': _lazy(u'Costa Rica'),
    'CZE': _lazy(u'Czech Republic'),
    'DEU': _lazy(u'Germany'),
    'ECU': _lazy(u'Ecuador'),
    'ESP': _lazy(u'Spain'),
    'FRA': _lazy(u'France'),
    'GBR': _lazy(u'United Kingdom'),
    'GRC': _lazy(u'Greece'),
    'GTM': _lazy(u'Guatemala'),
    'HUN': _lazy(u'Hungary'),
    'IND': _lazy(u'India'),
    'ITA': _lazy(u'Italy'),
    'JPN': _lazy(u'Japan'),
    'MEX': _lazy(u'Mexico'),
    'MNE': _lazy(u'Montenegro'),
    'NIC': _lazy(u'Nicaragua'),
    'PAN': _lazy(u'Panama'),
    'PER': _lazy(u'Peru'),
    'PHL': _lazy(u'Philippines'),
    'POL': _lazy(u'Poland'),
    'RUS': _lazy(u'Russia'),
    'SLV': _lazy(u'El Salvador'),
    'SRB': _lazy(u'Serbia'),
    'URY': _lazy(u'Uruguay'),
    'USA': _lazy(u'United States'),
    'VEN': _lazy(u'Venezuela'),
    'ZAF': _lazy(u'South Africa'),
}

for k, translation in lookup.items():
    country = countries.COUNTRY_DETAILS[k].copy()
    country['name'] = translation
    if country.get('ratingsbody'):
        country['ratingsbody'] = getattr(ratingsbodies, country['ratingsbody'])

    globals()[k] = type(k, (REGION,), country)

# Please adhere to the new region checklist when adding a new region:
# https://mana.mozilla.org/wiki/display/MARKET/How+to+add+a+new+region


# Create a list of tuples like so (in alphabetical order):
#
#     [('restofworld', <class 'mkt.constants.regions.RESTOFWORLD'>),
#      ('brazil', <class 'mkt.constants.regions.BR'>),
#      ('usa', <class 'mkt.constants.regions.USA'>)]
#

DEFINED = sorted(inspect.getmembers(sys.modules[__name__], inspect.isclass),
                 key=lambda x: getattr(x, 'slug', None))
REGIONS_CHOICES = (
    [('restofworld', RESTOFWORLD)] +
    sorted([(v.slug, v) for k, v in DEFINED if v.id and v.weight > -1],
           key=lambda x: x[1].weight, reverse=True)
)

BY_SLUG = sorted([v for k, v in DEFINED if v.id and v.weight > -1],
                 key=lambda v: v.slug)

REGIONS_CHOICES_SLUG = ([('restofworld', RESTOFWORLD)] +
                        [(v.slug, v) for v in BY_SLUG])
REGIONS_CHOICES_ID = ([(RESTOFWORLD.id, RESTOFWORLD)] +
                      [(v.id, v) for v in BY_SLUG])
# Rest of World last here so we can display it after all the other regions.
REGIONS_CHOICES_NAME = ([(v.id, v.name) for v in BY_SLUG] +
                        [(RESTOFWORLD.id, RESTOFWORLD.name)])

REGIONS_DICT = dict(REGIONS_CHOICES)
REGIONS_CHOICES_ID_DICT = dict(REGIONS_CHOICES_ID)
# Provide a dict for looking up the region by slug that includes aliases:
# - "worldwide" is an alias for RESTOFWORLD (bug 940561).
# - "gb" is an alias for GBR (bug 973883).
# Note: GBR is inserted into globals() above
REGION_LOOKUP = dict(
    REGIONS_DICT.items() +
    [('worldwide', RESTOFWORLD), ('gb', GBR)])  # noqa
ALL_REGIONS = frozenset(REGIONS_DICT.values())
ALL_REGION_IDS = sorted(REGIONS_CHOICES_ID_DICT.keys())

SPECIAL_REGIONS = [x for x in BY_SLUG if x.special]
SPECIAL_REGION_IDS = sorted(x.id for x in SPECIAL_REGIONS)

# Regions not including restofworld.
REGION_IDS = sorted(REGIONS_CHOICES_ID_DICT.keys())[1:]

GENERIC_RATING_REGION_SLUG = 'generic'


def ALL_REGIONS_WITH_CONTENT_RATINGS():
    """Regions that have ratings bodies."""
    return [x for x in ALL_REGIONS if x.ratingsbody]


def ALL_REGIONS_WITHOUT_CONTENT_RATINGS():
    """
    Regions without ratings bodies and fallback to the GENERIC rating body.
    """
    return set(ALL_REGIONS) - set(ALL_REGIONS_WITH_CONTENT_RATINGS())


def REGION_TO_RATINGS_BODY():
    """
    Return a map of region slugs to ratings body labels for use in
    serializers and to send to Fireplace.

    e.g. {'us': 'esrb', 'mx': 'esrb', 'es': 'pegi', 'br': 'classind'}.
    """
    # Create the mapping.
    region_to_bodies = {}
    for region in ALL_REGIONS_WITH_CONTENT_RATINGS():
        ratings_body_label = GENERIC_RATING_REGION_SLUG
        if region.ratingsbody:
            ratings_body_label = slugify_iarc_name(region.ratingsbody)
        region_to_bodies[region.slug] = ratings_body_label

    return region_to_bodies


def REGIONS_CHOICES_SORTED_BY_NAME():
    """Get the region choices and sort by name.

    Requires a function due to localisation.

    """

    # Avoid circular import.
    from mkt.regions.utils import remove_accents

    by_name = sorted([v for k, v in DEFINED if v.id and v.weight > -1],
                     key=lambda v: remove_accents(unicode(v.name)))
    return ([(v.id, v.name) for v in by_name] +
            [(RESTOFWORLD.id, RESTOFWORLD.name)])
