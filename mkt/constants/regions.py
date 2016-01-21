# -*- coding: utf-8 -*-
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
    'ABW': _lazy(u'Aruba'),
    'AFG': _lazy(u'Afghanistan'),
    'AGO': _lazy(u'Angola'),
    'AIA': _lazy(u'Anguilla'),
    'ALA': _lazy(u'Åland Islands'),
    'ALB': _lazy(u'Albania'),
    'AND': _lazy(u'Andorra'),
    'ARE': _lazy(u'United Arab Emirates'),
    'ARG': _lazy(u'Argentina'),
    'ARM': _lazy(u'Armenia'),
    'ASM': _lazy(u'American Samoa'),
    'ATA': _lazy(u'Antarctica'),
    'ATF': _lazy(u'French Southern Territories'),
    'ATG': _lazy(u'Antigua and Barbuda'),
    'AUS': _lazy(u'Australia'),
    'AUT': _lazy(u'Austria'),
    'AZE': _lazy(u'Azerbaijan'),
    'BDI': _lazy(u'Burundi'),
    'BEL': _lazy(u'Belgium'),
    'BEN': _lazy(u'Benin'),
    'BES': _lazy(u'Bonaire, Sint Eustatius and Saba'),
    'BFA': _lazy(u'Burkina Faso'),
    'BGD': _lazy(u'Bangladesh'),
    'BGR': _lazy(u'Bulgaria'),
    'BHR': _lazy(u'Bahrain'),
    'BHS': _lazy(u'Bahamas'),
    'BIH': _lazy(u'Bosnia and Herzegovina'),
    'BLM': _lazy(u'Saint Barthélemy'),
    'BLR': _lazy(u'Belarus'),
    'BLZ': _lazy(u'Belize'),
    'BMU': _lazy(u'Bermuda'),
    'BOL': _lazy(u'Bolivia, Plurinational State of'),
    'BRA': _lazy(u'Brazil'),
    'BRB': _lazy(u'Barbados'),
    'BRN': _lazy(u'Brunei Darussalam'),
    'BTN': _lazy(u'Bhutan'),
    'BVT': _lazy(u'Bouvet Island'),
    'BWA': _lazy(u'Botswana'),
    'CAF': _lazy(u'Central African Republic'),
    'CAN': _lazy(u'Canada'),
    'CCK': _lazy(u'Cocos (Keeling) Islands'),
    'CHE': _lazy(u'Switzerland'),
    'CHL': _lazy(u'Chile'),
    'CHN': _lazy(u'China'),
    'CIV': _lazy(u"Côte d'Ivoire"),
    'CMR': _lazy(u'Cameroon'),
    'COD': _lazy(u'Congo, Democratic Republic of the'),
    'COG': _lazy(u'Congo'),
    'COK': _lazy(u'Cook Islands'),
    'COL': _lazy(u'Colombia'),
    'COM': _lazy(u'Comoros'),
    'CPV': _lazy(u'Cabo Verde'),
    'CRI': _lazy(u'Costa Rica'),
    'CUB': _lazy(u'Cuba'),
    'CUW': _lazy(u'Curaçao'),
    'CXR': _lazy(u'Christmas Island'),
    'CYM': _lazy(u'Cayman Islands'),
    'CYP': _lazy(u'Cyprus'),
    'CZE': _lazy(u'Czech Republic'),
    'DEU': _lazy(u'Germany'),
    'DJI': _lazy(u'Djibouti'),
    'DMA': _lazy(u'Dominica'),
    'DNK': _lazy(u'Denmark'),
    'DOM': _lazy(u'Dominican Republic'),
    'DZA': _lazy(u'Algeria'),
    'ECU': _lazy(u'Ecuador'),
    'EGY': _lazy(u'Egypt'),
    'ERI': _lazy(u'Eritrea'),
    'ESH': _lazy(u'Western Sahara'),
    'ESP': _lazy(u'Spain'),
    'EST': _lazy(u'Estonia'),
    'ETH': _lazy(u'Ethiopia'),
    'FIN': _lazy(u'Finland'),
    'FJI': _lazy(u'Fiji'),
    'FLK': _lazy(u'Falkland Islands (Malvinas)'),
    'FRA': _lazy(u'France'),
    'FRO': _lazy(u'Faroe Islands'),
    'FSM': _lazy(u'Micronesia, Federated States of'),
    'GAB': _lazy(u'Gabon'),
    'GBR': _lazy(u'United Kingdom'),
    'GEO': _lazy(u'Georgia'),
    'GGY': _lazy(u'Guernsey'),
    'GHA': _lazy(u'Ghana'),
    'GIB': _lazy(u'Gibraltar'),
    'GIN': _lazy(u'Guinea-Conakry'),
    'GLP': _lazy(u'Guadeloupe'),
    'GMB': _lazy(u'Gambia'),
    'GNB': _lazy(u'Guinea-Bissau'),
    'GNQ': _lazy(u'Equatorial Guinea'),
    'GRC': _lazy(u'Greece'),
    'GRD': _lazy(u'Grenada'),
    'GRL': _lazy(u'Greenland'),
    'GTM': _lazy(u'Guatemala'),
    'GUF': _lazy(u'French Guiana'),
    'GUM': _lazy(u'Guam'),
    'GUY': _lazy(u'Guyana'),
    'HKG': _lazy(u'Hong Kong'),
    'HMD': _lazy(u'Heard Island and McDonald Islands'),
    'HND': _lazy(u'Honduras'),
    'HRV': _lazy(u'Croatia'),
    'HTI': _lazy(u'Haiti'),
    'HUN': _lazy(u'Hungary'),
    'IDN': _lazy(u'Indonesia'),
    'IMN': _lazy(u'Isle of Man'),
    'IND': _lazy(u'India'),
    'IOT': _lazy(u'British Indian Ocean Territory'),
    'IRL': _lazy(u'Ireland'),
    'IRQ': _lazy(u'Iraq'),
    'ISL': _lazy(u'Iceland'),
    'ISR': _lazy(u'Israel'),
    'ITA': _lazy(u'Italy'),
    'JAM': _lazy(u'Jamaica'),
    'JEY': _lazy(u'Jersey'),
    'JOR': _lazy(u'Jordan'),
    'JPN': _lazy(u'Japan'),
    'KAZ': _lazy(u'Kazakhstan'),
    'KEN': _lazy(u'Kenya'),
    'KGZ': _lazy(u'Kyrgyzstan'),
    'KHM': _lazy(u'Cambodia'),
    'KIR': _lazy(u'Kiribati'),
    'KNA': _lazy(u'Saint Kitts and Nevis'),
    'KOR': _lazy(u'Korea, Republic of'),
    'KWT': _lazy(u'Kuwait'),
    'LAO': _lazy(u"Lao People's Democratic Republic"),
    'LBN': _lazy(u'Lebanon'),
    'LBR': _lazy(u'Liberia'),
    'LBY': _lazy(u'Libya'),
    'LCA': _lazy(u'Saint Lucia'),
    'LIE': _lazy(u'Liechtenstein'),
    'LKA': _lazy(u'Sri Lanka'),
    'LSO': _lazy(u'Lesotho'),
    'LTU': _lazy(u'Lithuania'),
    'LUX': _lazy(u'Luxembourg'),
    'LVA': _lazy(u'Latvia'),
    'MAC': _lazy(u'Macao'),
    'MAF': _lazy(u'Saint Martin (French part)'),
    'MAR': _lazy(u'Morocco'),
    'MCO': _lazy(u'Monaco'),
    'MDA': _lazy(u'Moldova, Republic of'),
    'MDG': _lazy(u'Madagascar'),
    'MDV': _lazy(u'Maldives'),
    'MEX': _lazy(u'Mexico'),
    'MHL': _lazy(u'Marshall Islands'),
    'MKD': _lazy(u'Macedonia, the former Yugoslav Republic of'),
    'MLI': _lazy(u'Mali'),
    'MLT': _lazy(u'Malta'),
    'MMR': _lazy(u'Myanmar'),
    'MNE': _lazy(u'Montenegro'),
    'MNG': _lazy(u'Mongolia'),
    'MNP': _lazy(u'Northern Mariana Islands'),
    'MOZ': _lazy(u'Mozambique'),
    'MRT': _lazy(u'Mauritania'),
    'MSR': _lazy(u'Montserrat'),
    'MTQ': _lazy(u'Martinique'),
    'MUS': _lazy(u'Mauritius'),
    'MWI': _lazy(u'Malawi'),
    'MYS': _lazy(u'Malaysia'),
    'MYT': _lazy(u'Mayotte'),
    'NAM': _lazy(u'Namibia'),
    'NCL': _lazy(u'New Caledonia'),
    'NER': _lazy(u'Niger'),
    'NFK': _lazy(u'Norfolk Island'),
    'NGA': _lazy(u'Nigeria'),
    'NIC': _lazy(u'Nicaragua'),
    'NIU': _lazy(u'Niue'),
    'NLD': _lazy(u'Netherlands'),
    'NOR': _lazy(u'Norway'),
    'NPL': _lazy(u'Nepal'),
    'NRU': _lazy(u'Nauru'),
    'NZL': _lazy(u'New Zealand'),
    'OMN': _lazy(u'Oman'),
    'PAK': _lazy(u'Pakistan'),
    'PAN': _lazy(u'Panama'),
    'PCN': _lazy(u'Pitcairn'),
    'PER': _lazy(u'Peru'),
    'PHL': _lazy(u'Philippines'),
    'PLW': _lazy(u'Palau'),
    'PNG': _lazy(u'Papua New Guinea'),
    'POL': _lazy(u'Poland'),
    'PRI': _lazy(u'Puerto Rico'),
    'PRT': _lazy(u'Portugal'),
    'PRY': _lazy(u'Paraguay'),
    'PSE': _lazy(u'Palestine, State of'),
    'PYF': _lazy(u'French Polynesia'),
    'QAT': _lazy(u'Qatar'),
    'REU': _lazy(u'Réunion'),
    'ROU': _lazy(u'Romania'),
    'RUS': _lazy(u'Russia'),
    'RWA': _lazy(u'Rwanda'),
    'SAU': _lazy(u'Saudi Arabia'),
    'SDN': _lazy(u'Sudan'),
    'SEN': _lazy(u'Senegal'),
    'SGP': _lazy(u'Singapore'),
    'SGS': _lazy(u'South Georgia and the South Sandwich Islands'),
    'SHN': _lazy(u'Saint Helena, Ascension and Tristan da Cunha'),
    'SJM': _lazy(u'Svalbard and Jan Mayen'),
    'SLB': _lazy(u'Solomon Islands'),
    'SLE': _lazy(u'Sierra Leone'),
    'SLV': _lazy(u'El Salvador'),
    'SMR': _lazy(u'San Marino'),
    'SOM': _lazy(u'Somalia'),
    'SPM': _lazy(u'Saint Pierre and Miquelon'),
    'SRB': _lazy(u'Serbia'),
    'SSD': _lazy(u'South Sudan'),
    'STP': _lazy(u'Sao Tome and Principe'),
    'SUR': _lazy(u'Suriname'),
    'SVK': _lazy(u'Slovakia'),
    'SVN': _lazy(u'Slovenia'),
    'SWE': _lazy(u'Sweden'),
    'SWZ': _lazy(u'Swaziland'),
    'SXM': _lazy(u'Sint Maarten (Dutch part)'),
    'SYC': _lazy(u'Seychelles'),
    'SYR': _lazy(u'Syrian Arab Republic'),
    'TCA': _lazy(u'Turks and Caicos Islands'),
    'TCD': _lazy(u'Chad'),
    'TGO': _lazy(u'Togo'),
    'THA': _lazy(u'Thailand'),
    'TJK': _lazy(u'Tajikistan'),
    'TKL': _lazy(u'Tokelau'),
    'TKM': _lazy(u'Turkmenistan'),
    'TLS': _lazy(u'Timor-Leste'),
    'TON': _lazy(u'Tonga'),
    'TTO': _lazy(u'Trinidad and Tobago'),
    'TUN': _lazy(u'Tunisia'),
    'TUR': _lazy(u'Turkey'),
    'TUV': _lazy(u'Tuvalu'),
    'TWN': _lazy(u'Taiwan'),
    'TZA': _lazy(u'Tanzania'),
    'UGA': _lazy(u'Uganda'),
    'UKR': _lazy(u'Ukraine'),
    'UMI': _lazy(u'United States Minor Outlying Islands'),
    'URY': _lazy(u'Uruguay'),
    'USA': _lazy(u'United States'),
    'UZB': _lazy(u'Uzbekistan'),
    'VAT': _lazy(u'Holy See'),
    'VCT': _lazy(u'Saint Vincent and the Grenadines'),
    'VEN': _lazy(u'Venezuela'),
    'VGB': _lazy(u'Virgin Islands, British'),
    'VIR': _lazy(u'Virgin Islands, U.S.'),
    'VNM': _lazy(u'Viet Nam'),
    'VUT': _lazy(u'Vanuatu'),
    'WLF': _lazy(u'Wallis and Futuna'),
    'WSM': _lazy(u'Samoa'),
    'YEM': _lazy(u'Yemen'),
    'ZAF': _lazy(u'South Africa'),
    'ZMB': _lazy(u'Zambia'),
    'ZWE': _lazy(u'Zimbabwe'),
}

for k, translation in lookup.items():
    country = countries.COUNTRY_DETAILS[k].copy()
    country['name'] = translation
    if country.get('ratingsbody'):
        country['ratingsbody'] = getattr(ratingsbodies, country['ratingsbody'])

    locals()[k] = type(k, (REGION,), country)

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
# Note: GBR is inserted into locals() above
REGION_LOOKUP = dict(
    REGIONS_DICT.items() +
    [('worldwide', RESTOFWORLD), ('gb', locals()['GBR'])])
ALL_REGIONS = frozenset(REGIONS_DICT.values())
ALL_REGION_IDS = sorted(REGIONS_CHOICES_ID_DICT.keys())

SPECIAL_REGIONS = [x for x in BY_SLUG if x.special]
SPECIAL_REGION_IDS = sorted(x.id for x in SPECIAL_REGIONS)

# Regions not including restofworld.
REGION_IDS = sorted(REGIONS_CHOICES_ID_DICT.keys())[1:]

# Mature regions.
MATURE_REGION_IDS = sorted(x.id for x in ALL_REGIONS if not x.adolescent)

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


def REGIONS_LIST_SORTED_BY_NAME():
    """Get the region list and sort by name.

    Requires a function due to localisation.

    """

    # Avoid circular import.
    from mkt.regions.utils import remove_accents

    by_name = sorted([v for k, v in DEFINED if v.id and v.weight > -1],
                     key=lambda v: remove_accents(unicode(v.name)))
    by_name.append(RESTOFWORLD)
    return by_name


def REGIONS_CHOICES_SORTED_BY_NAME():
    """Get the region choices and sort by name.

    Requires a function due to localisation.

    """
    return [(v.id, v.name) for v in REGIONS_LIST_SORTED_BY_NAME()]


REGIONS_BY_MCC = {c['mcc']: c['slug']
                  for c in countries.COUNTRY_DETAILS.itervalues()
                  if 'mcc' in c}
