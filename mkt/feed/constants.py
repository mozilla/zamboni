FEEDAPP_ICON = 'icon'
FEEDAPP_IMAGE = 'image'
FEEDAPP_DESC = 'description'
FEEDAPP_QUOTE = 'quote'
FEEDAPP_PREVIEW = 'preview'
FEEDAPP_TYPES = (
    FEEDAPP_ICON,
    FEEDAPP_IMAGE,
    FEEDAPP_DESC,
    FEEDAPP_QUOTE,
    FEEDAPP_PREVIEW,
)
FEEDAPP_TYPE_CHOICES = [(c, c) for c in FEEDAPP_TYPES]

# Editorial Brand types, represented as a list of slug-like strings. L10n for
# these are handled on the client side.
BRAND_TYPES = (
    'apps-for-albania',
    'apps-for-argentina',
    'apps-for-bangladesh',
    'apps-for-brazil',
    'apps-for-bulgaria',
    'apps-for-chile',
    'apps-for-china',
    'apps-for-colombia',
    'apps-for-costa-rica',
    'apps-for-croatia',
    'apps-for-czech-republic',
    'apps-for-ecuador',
    'apps-for-el-salvador',
    'apps-for-france',
    'apps-for-germany',
    'apps-for-greece',
    'apps-for-hungary',
    'apps-for-india',
    'apps-for-italy',
    'apps-for-japan',
    'apps-for-macedonia',
    'apps-for-mexico',
    'apps-for-montenegro',
    'apps-for-nicaragua',
    'apps-for-panama',
    'apps-for-peru',
    'apps-for-poland',
    'apps-for-russia',
    'apps-for-serbia',
    'apps-for-south-africa',
    'apps-for-spain',
    'apps-for-uruguay',
    'apps-for-venezuela',
    'arts-entertainment',
    'book',
    'creativity',
    'education',
    'games',
    'groundbreaking',
    'health-fitness',
    'hidden-gem',
    'lifestyle',
    'local-favorite',
    'maps-navigation',
    'music',
    'mystery-app',
    'news-weather',
    'photo-video',
    'shopping',
    'social',
    'sports',
    'tools-time-savers',
    'travel',
    'work-business',
)
BRAND_TYPE_CHOICES = [(c, c) for c in BRAND_TYPES]


# Editorial Brand layouts
BRAND_GRID = 'grid'
BRAND_LIST = 'list'
BRAND_LAYOUTS = (
    BRAND_GRID,
    BRAND_LIST
)
BRAND_LAYOUT_CHOICES = [(c, c) for c in BRAND_LAYOUTS]

COLLECTION_PROMO = 'promo'
COLLECTION_LISTING = 'listing'
COLLECTION_TYPES = (
    COLLECTION_PROMO,
    COLLECTION_LISTING,
)
COLLECTION_TYPE_CHOICES = [(c, c) for c in COLLECTION_TYPES]

FEED_TYPE_APP = 'app'
FEED_TYPE_BRAND = 'brand'
FEED_TYPE_COLL = 'collection'
FEED_TYPE_SHELF = 'shelf'

# Number of apps we need to deserialize for the homepage/actual feed.
HOME_NUM_APPS_BRAND = 6
HOME_NUM_APPS_LISTING_COLL = 6
HOME_NUM_APPS_PROMO_COLL = 3
HOME_NUM_APPS_SHELF = 0

# Minimum number of apps needed after filtering to be displayed for colls.
MIN_APPS_COLLECTION = 3
