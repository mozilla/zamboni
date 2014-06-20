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
    'apps-for-croatia',
    'apps-for-czechoslovakia',
    'apps-for-ecuador',
    'apps-for-education',
    'apps-for-el-salvador',
    'apps-for-germany',
    'apps-for-greece',
    'apps-for-guatemala',
    'apps-for-hungary',
    'apps-for-india',
    'apps-for-italy',
    'apps-for-macedonia',
    'apps-for-mexico',
    'apps-for-montenegro',
    'apps-for-nicaragua',
    'apps-for-panama',
    'apps-for-per',
    'apps-for-poland',
    'apps-for-russia',
    'apps-for-serbia',
    'apps-for-south-africa',
    'apps-for-spain',
    'apps-for-uruguay',
    'apps-for-venezuela',
    'arts-entertainment',
    'arts-entertainment-spotlight',
    'be-more-productive',
    'better-business',
    'book',
    'editors-pick',
    'education',
    'education-spotlight',
    'featured-app-for-work-business',
    'featured-camera-app',
    'featured-creativity-app',
    'featured-lifestyle-app',
    'featured-social-app',
    'for-music-lovers',
    'for-travelers',
    'games',
    'get-connected',
    'get-creative',
    'get-things-done',
    'getting-around',
    'great-game',
    'great-read',
    'groundbreaking-app',
    'health-fitness',
    'healthy-living',
    'hidden-gem',
    'hot-game',
    'instant-fun',
    'lifestyle',
    'lifestyle-culture',
    'live-healthy',
    'local-community-favorites',
    'local-favorite',
    'maps-navigation',
    'maps-navigation-spotlight',
    'music',
    'mystery-app',
    'news-weather',
    'news-weather-spotlight',
    'photo-video',
    'play-this-game-right-now',
    'shopping',
    'smart-shopping-apps',
    'social',
    'sports',
    'staff-pick',
    'the-sporting-life',
    'todays-top-app',
    'tools-time-savers',
    'travel',
    'travel-guide',
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

FEED_COLOR_CHOICES = (
    ('#B90000', 'Raring Red'),
    ('#FF4E00', 'Oneric Orange'),
    ('#CD6723', 'Breezy Brown'),
    ('#00AACC', 'Blistering Blue'),
    ('#5F9B0A', 'Gusty Green'),
    ('#2C393B', 'Intrepid Indigo'),
)

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
