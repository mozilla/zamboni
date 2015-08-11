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
STATUS_UNLISTED = 16

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
    STATUS_PUBLIC: _(u'Published'),
    STATUS_DISABLED: _(u'Banned from Marketplace'),
    STATUS_DELETED: _(u'Deleted'),
    STATUS_REJECTED: _(u'Rejected'),
    # Approved, but the developer would like to put it public when they want.
    # The need to go to the marketplace and actualy make it public.
    STATUS_APPROVED: _(u'Approved but private'),
    STATUS_BLOCKED: _(u'Blocked'),
    STATUS_UNLISTED: _(u'Unlisted'),
}


# Marketplace file status terms.
MKT_STATUS_FILE_CHOICES = STATUS_CHOICES.copy()
MKT_STATUS_FILE_CHOICES[STATUS_DISABLED] = _(u'Obsolete')
MKT_STATUS_FILE_CHOICES[STATUS_APPROVED] = _(u'Approved')
MKT_STATUS_FILE_CHOICES[STATUS_PUBLIC] = _(u'Published')

# We need to expose nice values that aren't localisable.
STATUS_CHOICES_API = {
    STATUS_NULL: 'incomplete',
    STATUS_PENDING: 'pending',
    STATUS_PUBLIC: 'public',
    STATUS_DISABLED: 'disabled',  # TODO: Change to 'banned' for API v2.
    STATUS_DELETED: 'deleted',
    STATUS_REJECTED: 'rejected',
    STATUS_APPROVED: 'waiting',  # TODO: Change to 'private' for API v2.
    STATUS_BLOCKED: 'blocked',
    STATUS_UNLISTED: 'unlisted',
}

STATUS_CHOICES_API_LOOKUP = {
    'incomplete': STATUS_NULL,
    'pending': STATUS_PENDING,
    'public': STATUS_PUBLIC,
    'disabled': STATUS_DISABLED,  # TODO: Change to 'banned' for API v2.
    'deleted': STATUS_DELETED,
    'rejected': STATUS_REJECTED,
    'waiting': STATUS_APPROVED,  # TODO: Change to 'private' for API v2.
    'blocked': STATUS_BLOCKED,
    'unlisted': STATUS_UNLISTED,
}

STATUS_CHOICES_API_v2 = {
    STATUS_NULL: 'incomplete',
    STATUS_PENDING: 'pending',
    STATUS_PUBLIC: 'public',
    STATUS_DISABLED: 'banned',
    STATUS_DELETED: 'deleted',
    STATUS_REJECTED: 'rejected',
    STATUS_APPROVED: 'private',
    STATUS_BLOCKED: 'blocked',
    STATUS_UNLISTED: 'unlisted',
}

STATUS_CHOICES_API_LOOKUP_v2 = {
    'incomplete': STATUS_NULL,
    'pending': STATUS_PENDING,
    'public': STATUS_PUBLIC,
    'banned': STATUS_DISABLED,
    'deleted': STATUS_DELETED,
    'rejected': STATUS_REJECTED,
    'private': STATUS_APPROVED,
    'blocked': STATUS_BLOCKED,
    'unlisted': STATUS_UNLISTED,
}

# Publishing types.
PUBLISH_IMMEDIATE = 0
PUBLISH_HIDDEN = 1
PUBLISH_PRIVATE = 2

REVIEWED_STATUSES = (STATUS_PUBLIC, STATUS_APPROVED, STATUS_UNLISTED)
UNREVIEWED_STATUSES = (STATUS_PENDING,)
VALID_STATUSES = (STATUS_PENDING, STATUS_PUBLIC, STATUS_UNLISTED,
                  STATUS_APPROVED)
# LISTED_STATUSES are statuses that should return a 200 on the app detail page
# for anonymous users.
LISTED_STATUSES = (STATUS_PUBLIC, STATUS_UNLISTED)

# An add-on in one of these statuses can become premium.
PREMIUM_STATUSES = (STATUS_NULL, STATUS_PENDING)

# Newly submitted apps begin life at this status.
WEBAPPS_UNREVIEWED_STATUS = STATUS_PENDING

# These apps have been approved and are listed; or could be without further
# review.
WEBAPPS_APPROVED_STATUSES = (STATUS_PUBLIC, STATUS_UNLISTED, STATUS_APPROVED)

# An app with this status makes its detail page "invisible".
WEBAPPS_UNLISTED_STATUSES = (STATUS_DISABLED, STATUS_PENDING, STATUS_APPROVED,
                             STATUS_REJECTED)

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
AUTHOR_CHOICES_NAMES = dict(AUTHOR_CHOICES)


# WEBAPP Types
WEBAPP_HOSTED = 1
WEBAPP_PACKAGED = 2
WEBAPP_PRIVILEGED = 3

WEBAPP_TYPES = {
    WEBAPP_HOSTED: 'hosted',
    WEBAPP_PACKAGED: 'packaged',
    WEBAPP_PRIVILEGED: 'privileged',
}
WEBAPP_TYPES_LOOKUP = dict((v, k) for k, v in WEBAPP_TYPES.items())

WEBAPP_FREE = 0
WEBAPP_PREMIUM = 1
WEBAPP_PREMIUM_INAPP = 2
WEBAPP_FREE_INAPP = 3
# The webapp will have payments, but they aren't using our payment system.
WEBAPP_OTHER_INAPP = 4

WEBAPP_PREMIUM_TYPES = {
    WEBAPP_FREE: _('Free'),
    WEBAPP_PREMIUM: _('Premium'),
    WEBAPP_PREMIUM_INAPP: _('Premium with in-app payments'),
    WEBAPP_FREE_INAPP: _('Free with in-app payments'),
    WEBAPP_OTHER_INAPP: _("I'll use my own system for in-app payments")
}

# Non-locale versions for the API.
WEBAPP_PREMIUM_API = {
    WEBAPP_FREE: 'free',
    WEBAPP_PREMIUM: 'premium',
    WEBAPP_PREMIUM_INAPP: 'premium-inapp',
    WEBAPP_FREE_INAPP: 'free-inapp',
    WEBAPP_OTHER_INAPP: 'other',
}
WEBAPP_PREMIUM_API_LOOKUP = dict((v, k) for k, v in WEBAPP_PREMIUM_API.items())

# Apps that require some sort of payment prior to installing.
WEBAPP_PREMIUMS = (WEBAPP_PREMIUM, WEBAPP_PREMIUM_INAPP)
# Apps that do *not* require a payment prior to installing.
WEBAPP_FREES = (WEBAPP_FREE, WEBAPP_FREE_INAPP, WEBAPP_OTHER_INAPP)
WEBAPP_INAPPS = (WEBAPP_PREMIUM_INAPP, WEBAPP_FREE_INAPP)
WEBAPP_HAS_PAYMENTS = (WEBAPP_FREE_INAPP, WEBAPP_PREMIUM, WEBAPP_PREMIUM_INAPP)

# Edit webapp information
MAX_TAGS = 20
MIN_TAG_LENGTH = 2
MAX_CATEGORIES = 2

# Icon sizes we want to generate and expose in the API.
CONTENT_ICON_SIZES = [32, 48, 64, 128]

# Promo img sizes we want to generate and expose in the API.
PROMO_IMG_SIZES = [320, 640, 1050]

PROMO_IMG_MINIMUMS = (1050, 300)

# Preview upload sizes [thumb, full]
WEBAPP_PREVIEW_SIZES = [(200, 150), (700, 525)]

# Accepted image MIME-types
IMG_TYPES = ('image/png', 'image/jpeg', 'image/jpg')
VIDEO_TYPES = ('video/webm',)

# Editor Tools
EDITOR_VIEWING_INTERVAL = 8  # How often we ping for "who's watching?"

# For use in urls.
WEBAPP_UUID = r'(?P<uuid>[\w]{8}-[\w]{4}-[\w]{4}-[\w]{4}-[\w]{12})'
APP_SLUG = r"""(?P<app_slug>[^/<>"']+)"""

# Reviewer Incentive Scores.
# Note: Don't change these since they're used as keys in the database.
REVIEWED_MANUAL = 0
REVIEWED_WEBAPP_HOSTED = 70
REVIEWED_WEBAPP_PACKAGED = 71
REVIEWED_WEBAPP_REREVIEW = 72
REVIEWED_WEBAPP_UPDATE = 73
REVIEWED_WEBAPP_PRIVILEGED = 74
REVIEWED_WEBAPP_PRIVILEGED_UPDATE = 75
REVIEWED_WEBAPP_PLATFORM_EXTRA = 76  # Not used as a key
REVIEWED_APP_REVIEW = 81
REVIEWED_APP_REVIEW_UNDO = 82
REVIEWED_WEBAPP_TARAKO = 90
REVIEWED_APP_ABUSE_REPORT = 100
REVIEWED_WEBSITE_ABUSE_REPORT = 101

REVIEWED_CHOICES = {
    REVIEWED_MANUAL: _('Manual Reviewer Points'),
    REVIEWED_WEBAPP_HOSTED: _('Web App Review'),
    REVIEWED_WEBAPP_PACKAGED: _('Packaged App Review'),
    REVIEWED_WEBAPP_PRIVILEGED: _('Privileged App Review'),
    REVIEWED_WEBAPP_REREVIEW: _('Web App Re-review'),
    REVIEWED_WEBAPP_UPDATE: _('Updated Packaged App Review'),
    REVIEWED_WEBAPP_PRIVILEGED_UPDATE: _('Updated Privileged App Review'),
    REVIEWED_APP_REVIEW: _('Moderated App Review'),
    REVIEWED_APP_REVIEW_UNDO: _('App Review Moderation Reverted'),
    REVIEWED_WEBAPP_TARAKO: _('Tarako App Review'),
    REVIEWED_APP_ABUSE_REPORT: _('App Abuse Report Read'),
    REVIEWED_WEBSITE_ABUSE_REPORT: _('Website Abuse Report Read'),
}

REVIEWED_SCORES = {
    REVIEWED_MANUAL: 0,
    REVIEWED_WEBAPP_HOSTED: 60,
    REVIEWED_WEBAPP_PACKAGED: 60,
    REVIEWED_WEBAPP_PRIVILEGED: 120,
    REVIEWED_WEBAPP_REREVIEW: 30,
    REVIEWED_WEBAPP_UPDATE: 40,
    REVIEWED_WEBAPP_PRIVILEGED_UPDATE: 80,
    REVIEWED_APP_REVIEW: 1,
    REVIEWED_APP_REVIEW_UNDO: -1,  # -REVIEWED_APP_REVIEW
    REVIEWED_WEBAPP_TARAKO: 30,
    REVIEWED_WEBAPP_PLATFORM_EXTRA: 10,
    REVIEWED_APP_ABUSE_REPORT: 2,
    REVIEWED_WEBSITE_ABUSE_REPORT: 2,
}

REVIEWED_MARKETPLACE = (
    REVIEWED_WEBAPP_HOSTED,
    REVIEWED_WEBAPP_PACKAGED,
    REVIEWED_WEBAPP_PRIVILEGED,
    REVIEWED_WEBAPP_REREVIEW,
    REVIEWED_WEBAPP_UPDATE,
    REVIEWED_WEBAPP_PRIVILEGED_UPDATE,
    REVIEWED_APP_REVIEW,
    REVIEWED_APP_REVIEW_UNDO,
    REVIEWED_WEBAPP_TARAKO,
    REVIEWED_APP_ABUSE_REPORT,
    REVIEWED_WEBSITE_ABUSE_REPORT,
)

REVIEWED_LEVELS = [
    {'name': _('Level 1'), 'points': 2160},
    {'name': _('Level 2'), 'points': 4320},
    {'name': _('Level 3'), 'points': 8700},
    {'name': _('Level 4'), 'points': 21000},
    {'name': _('Level 5'), 'points': 45000},
    {'name': _('Level 6'), 'points': 96000},
    {'name': _('Level 7'), 'points': 300000},
    {'name': _('Level 8'), 'points': 1200000},
    {'name': _('Level 9'), 'points': 3000000},
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

LOGIN_SOURCE_LOOKUP = {
    LOGIN_SOURCE_UNKNOWN: 'unknown',
    LOGIN_SOURCE_BROWSERID: 'persona',
    LOGIN_SOURCE_MMO_BROWSERID: 'mmo-persona',
    LOGIN_SOURCE_AMO_BROWSERID: 'amo-persona',
    LOGIN_SOURCE_FXA: 'firefox-accounts',
    LOGIN_SOURCE_WEBPAY: 'webpay',
}
# Add slug ~> id to the dict so lookups can be done with id or slug.
for source_id, source_slug in LOGIN_SOURCE_LOOKUP.items():
    LOGIN_SOURCE_LOOKUP[source_slug] = source_id

# These are logins that use BrowserID.
LOGIN_SOURCE_BROWSERIDS = [LOGIN_SOURCE_BROWSERID, LOGIN_SOURCE_AMO_BROWSERID,
                           LOGIN_SOURCE_MMO_BROWSERID, LOGIN_SOURCE_WEBPAY]
