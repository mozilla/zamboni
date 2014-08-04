from tower import ugettext_lazy as _


# Add-on and File statuses.
STATUS_NULL = 0
STATUS_PENDING = 2
STATUS_PUBLIC = 4
STATUS_DISABLED = 5
STATUS_DELETED = 11
STATUS_REJECTED = 12
STATUS_APPROVED = 13
STATUS_BLOCKED = 15

# AMO-only statuses. Kept here only for memory and to not re-use the IDs.
_STATUS_UNREVIEWED = 1
_STATUS_NOMINATED = 3
_STATUS_LISTED = 6  # See bug 616242.
_STATUS_BETA = 7
_STATUS_LITE = 8
_STATUS_LITE_AND_NOMINATED = 9
_STATUS_PURGATORY = 10  # A temporary home; bug 614686
_STATUS_REVIEW_PENDING = 14  # Themes queue, reviewed, needs further action.

STATUS_CHOICES = {
    STATUS_NULL: _(u'Incomplete'),
    STATUS_PENDING: _(u'Pending approval'),
    STATUS_PUBLIC: _(u'Fully Reviewed'),
    STATUS_DISABLED: _(u'Disabled by Mozilla'),
    STATUS_DELETED: _(u'Deleted'),
    STATUS_REJECTED: _(u'Rejected'),
    # Approved, but the developer would like to put it public when they want.
    # The need to go to the marketplace and actualy make it public.
    STATUS_APPROVED: _(u'Approved but waiting'),
    STATUS_BLOCKED: _(u'Blocked'),
}


# Marketplace app status terms.
MKT_STATUS_CHOICES = STATUS_CHOICES.copy()
MKT_STATUS_CHOICES[STATUS_PUBLIC] = _(u'Published')
MKT_STATUS_CHOICES[STATUS_APPROVED] = _(u'Approved but unpublished')

# Marketplace file status terms.
MKT_STATUS_FILE_CHOICES = MKT_STATUS_CHOICES.copy()
MKT_STATUS_FILE_CHOICES[STATUS_DISABLED] = _(u'Obsolete')

# We need to expose nice values that aren't localisable.
STATUS_CHOICES_API = {
    STATUS_NULL: 'incomplete',
    STATUS_PENDING: 'pending',
    STATUS_PUBLIC: 'public',
    STATUS_DISABLED: 'disabled',
    STATUS_DELETED: 'deleted',
    STATUS_REJECTED: 'rejected',
    STATUS_APPROVED: 'waiting',
    STATUS_BLOCKED: 'blocked',
}

STATUS_CHOICES_API_LOOKUP = {
    'incomplete': STATUS_NULL,
    'pending': STATUS_PENDING,
    'public': STATUS_PUBLIC,
    'disabled': STATUS_DISABLED,
    'deleted': STATUS_DELETED,
    'rejected': STATUS_REJECTED,
    'waiting': STATUS_APPROVED,
    'blocked': STATUS_BLOCKED,
}

# Publishing types.
PUBLISH_IMMEDIATE = 0
PUBLISH_HIDDEN = 1
PUBLISH_PRIVATE = 2

REVIEWED_STATUSES = (STATUS_PUBLIC, STATUS_APPROVED)
UNREVIEWED_STATUSES = (STATUS_PENDING,)
VALID_STATUSES = (STATUS_PENDING, STATUS_PUBLIC, STATUS_APPROVED)
# We don't show addons/versions with UNREVIEWED_STATUS in public.
LISTED_STATUSES = tuple(st for st in VALID_STATUSES
                        if st not in (STATUS_PENDING, STATUS_APPROVED))

# An addon in one of these statuses is awaiting a review.
STATUS_UNDER_REVIEW = (STATUS_PENDING,)

# An add-on in one of these statuses can become premium.
PREMIUM_STATUSES = (STATUS_NULL,) + STATUS_UNDER_REVIEW

# Newly submitted apps begin life at this status.
WEBAPPS_UNREVIEWED_STATUS = STATUS_PENDING

# These apps have been approved and are listed; or could be without further
# review
WEBAPPS_APPROVED_STATUSES = (STATUS_PUBLIC, STATUS_APPROVED)

# An app with this status makes its detail page "invisible".
WEBAPPS_UNLISTED_STATUSES = (STATUS_DISABLED, STATUS_PENDING,
                             STATUS_APPROVED, STATUS_REJECTED)

# The only statuses we use in the marketplace.
MARKET_STATUSES = (STATUS_NULL, STATUS_PENDING, STATUS_PUBLIC, STATUS_DISABLED,
                   STATUS_DELETED, STATUS_REJECTED, STATUS_APPROVED,
                   STATUS_BLOCKED)

# These apps shouldn't be considered anymore in mass-emailing etc.
WEBAPPS_EXCLUDED_STATUSES = (STATUS_DISABLED, STATUS_DELETED, STATUS_REJECTED)

# Add-on author roles.
AUTHOR_ROLE_VIEWER = 1
AUTHOR_ROLE_DEV = 4
AUTHOR_ROLE_OWNER = 5
AUTHOR_ROLE_SUPPORT = 6

AUTHOR_CHOICES = (
    (AUTHOR_ROLE_OWNER, _(u'Owner')),
    (AUTHOR_ROLE_DEV, _(u'Developer')),
    (AUTHOR_ROLE_VIEWER, _(u'Viewer')),
    (AUTHOR_ROLE_SUPPORT, _(u'Support')),
)

# Addon types
ADDON_ANY = 0
ADDON_EXTENSION = 1
ADDON_THEME = 2
ADDON_DICT = 3
ADDON_SEARCH = 4
ADDON_LPAPP = 5
ADDON_LPADDON = 6
ADDON_PLUGIN = 7
ADDON_API = 8  # not actually a type but used to identify extensions + themes
ADDON_PERSONA = 9
ADDON_WEBAPP = 11  # Calling this ADDON_* is gross but we've gotta ship code.

# Addon type groupings.
GROUP_TYPE_ADDON = [ADDON_EXTENSION, ADDON_DICT, ADDON_SEARCH, ADDON_LPAPP,
                    ADDON_LPADDON, ADDON_PLUGIN, ADDON_API]
GROUP_TYPE_THEME = [ADDON_THEME, ADDON_PERSONA]
GROUP_TYPE_WEBAPP = [ADDON_WEBAPP]

# Singular
ADDON_TYPE = {
    ADDON_ANY: _(u'Any'),
    ADDON_EXTENSION: _(u'Extension'),
    ADDON_THEME: _(u'Complete Theme'),
    ADDON_DICT: _(u'Dictionary'),
    ADDON_SEARCH: _(u'Search Engine'),
    ADDON_PLUGIN: _(u'Plugin'),
    ADDON_LPAPP: _(u'Language Pack (Application)'),
    ADDON_PERSONA: _(u'Theme'),
    ADDON_WEBAPP: _(u'App'),
}

# Plural
ADDON_TYPES = {
    ADDON_ANY: _(u'Any'),
    ADDON_EXTENSION: _(u'Extensions'),
    ADDON_THEME: _(u'Complete Themes'),
    ADDON_DICT: _(u'Dictionaries'),
    ADDON_SEARCH: _(u'Search Tools'),
    ADDON_PLUGIN: _(u'Plugins'),
    ADDON_LPAPP: _(u'Language Packs (Application)'),
    ADDON_PERSONA: _(u'Themes'),
    ADDON_WEBAPP: _(u'Apps'),
}

MARKETPLACE_TYPES = [ADDON_WEBAPP]

# ADDON_WEBAPP Types
ADDON_WEBAPP_HOSTED = 1
ADDON_WEBAPP_PACKAGED = 2
ADDON_WEBAPP_PRIVILEGED = 3

ADDON_WEBAPP_TYPES = {
    ADDON_WEBAPP_HOSTED: 'hosted',
    ADDON_WEBAPP_PACKAGED: 'packaged',
    ADDON_WEBAPP_PRIVILEGED: 'privileged',
}
ADDON_WEBAPP_TYPES_LOOKUP = dict((v, k) for k, v in ADDON_WEBAPP_TYPES.items())

# Marketplace search API addon types.
MKT_ADDON_TYPES_API = {
    'app': ADDON_WEBAPP,
}

ADDON_FREE = 0
ADDON_PREMIUM = 1
ADDON_PREMIUM_INAPP = 2
ADDON_FREE_INAPP = 3
# The addon will have payments, but they aren't using our payment system.
ADDON_OTHER_INAPP = 4

ADDON_PREMIUM_TYPES = {
    ADDON_FREE: _('Free'),
    ADDON_PREMIUM: _('Premium'),
    ADDON_PREMIUM_INAPP: _('Premium with in-app payments'),
    ADDON_FREE_INAPP: _('Free with in-app payments'),
    ADDON_OTHER_INAPP: _("I'll use my own system for in-app payments")
}

# Non-locale versions for the API.
ADDON_PREMIUM_API = {
    ADDON_FREE: 'free',
    ADDON_PREMIUM: 'premium',
    ADDON_PREMIUM_INAPP: 'premium-inapp',
    ADDON_FREE_INAPP: 'free-inapp',
    ADDON_OTHER_INAPP: 'other',
}
ADDON_PREMIUM_API_LOOKUP = dict((v, k) for k, v in ADDON_PREMIUM_API.items())

# Apps that require some sort of payment prior to installing.
ADDON_PREMIUMS = (ADDON_PREMIUM, ADDON_PREMIUM_INAPP)
# Apps that do *not* require a payment prior to installing.
ADDON_FREES = (ADDON_FREE, ADDON_FREE_INAPP, ADDON_OTHER_INAPP)
ADDON_INAPPS = (ADDON_PREMIUM_INAPP, ADDON_FREE_INAPP)
ADDON_BECOME_PREMIUM = (ADDON_EXTENSION, ADDON_THEME, ADDON_DICT,
                        ADDON_LPAPP, ADDON_WEBAPP)
ADDON_HAS_PAYMENTS = (ADDON_FREE_INAPP, ADDON_PREMIUM, ADDON_PREMIUM_INAPP)

# Edit addon information
MAX_TAGS = 20
MIN_TAG_LENGTH = 2
MAX_CATEGORIES = 2

# Icon sizes we want to generate and expose in the API.
APP_ICON_SIZES = [32, 48, 64, 128]

# Preview upload sizes [thumb, full]
ADDON_PREVIEW_SIZES = [(200, 150), (700, 525)]

# Accepted image MIME-types
IMG_TYPES = ('image/png', 'image/jpeg', 'image/jpg')
VIDEO_TYPES = ('video/webm',)

# Editor Tools
EDITOR_VIEWING_INTERVAL = 8  # How often we ping for "who's watching?"

# For use in urls.
ADDON_UUID = r'(?P<uuid>[\w]{8}-[\w]{4}-[\w]{4}-[\w]{4}-[\w]{12})'
APP_SLUG = r"""(?P<app_slug>[^/<>"']+)"""

# Reviewer Incentive Scores.
# Note: Don't change these since they're used as keys in the database.
REVIEWED_MANUAL = 0
REVIEWED_WEBAPP_HOSTED = 70
REVIEWED_WEBAPP_PACKAGED = 71
REVIEWED_WEBAPP_REREVIEW = 72
REVIEWED_WEBAPP_UPDATE = 73
REVIEWED_APP_REVIEW = 81

REVIEWED_CHOICES = {
    REVIEWED_MANUAL: _('Manual Reviewer Points'),
    REVIEWED_WEBAPP_HOSTED: _('Web App Review'),
    REVIEWED_WEBAPP_PACKAGED: _('Packaged App Review'),
    REVIEWED_WEBAPP_REREVIEW: _('Web App Re-review'),
    REVIEWED_WEBAPP_UPDATE: _('Updated Packaged App Review'),
    REVIEWED_APP_REVIEW: _('Moderated App Review'),
}

REVIEWED_SCORES = {
    REVIEWED_MANUAL: 0,
    REVIEWED_WEBAPP_HOSTED: 60,
    REVIEWED_WEBAPP_PACKAGED: 120,
    REVIEWED_WEBAPP_REREVIEW: 30,
    REVIEWED_WEBAPP_UPDATE: 80,
    REVIEWED_APP_REVIEW: 1,
}

REVIEWED_MARKETPLACE = (
    REVIEWED_WEBAPP_HOSTED,
    REVIEWED_WEBAPP_PACKAGED,
    REVIEWED_WEBAPP_REREVIEW,
    REVIEWED_WEBAPP_UPDATE,
    REVIEWED_APP_REVIEW,
)

REVIEWED_LEVELS = [
    {'name': _('Level 1'), 'points': 2160},
    {'name': _('Level 2'), 'points': 4320},
    {'name': _('Level 3'), 'points': 8700},
    {'name': _('Level 4'), 'points': 21000},
    {'name': _('Level 5'), 'points': 45000},
    {'name': _('Level 6'), 'points': 96000},
]

# Login credential source. We'll also include the site source in that.
# All the old existing AMO users and anyone before we started tracking this.
LOGIN_SOURCE_UNKNOWN = 0
# Most likely everyone who signed up for the marketplace.
LOGIN_SOURCE_BROWSERID = 1
# Everyone who signed up for the marketplace using BrowserID.
LOGIN_SOURCE_MMO_BROWSERID = 2
# Everyone who signed up for AMO once it uses BrowserID.
LOGIN_SOURCE_AMO_BROWSERID = 3
# Signups via Firefox Accounts.
LOGIN_SOURCE_FXA = 4
# Signups via Webpay Purchases
LOGIN_SOURCE_WEBPAY = 5

# These are logins that use BrowserID.
LOGIN_SOURCE_BROWSERIDS = [LOGIN_SOURCE_BROWSERID, LOGIN_SOURCE_AMO_BROWSERID,
                           LOGIN_SOURCE_MMO_BROWSERID, LOGIN_SOURCE_WEBPAY]
