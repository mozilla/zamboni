from tower import ugettext_lazy as _


# To add a note type:
# - assign it a incremented number (MY_NOTE_TYPE = 42)
# - give it a translation in NOTE_TYPES
# - if adding from amo/log.py, add it to ACTION_MAP
# - add the translation to Commbadge settings

# Faith of the seven.
NO_ACTION = 0
APPROVAL = 1
REJECTION = 2
DISABLED = 3
MORE_INFO_REQUIRED = 4
ESCALATION = 5
REVIEWER_COMMENT = 6
RESUBMISSION = 7
APPROVE_VERSION_WAITING = 8
ESCALATION_HIGH_ABUSE = 9
ESCALATION_HIGH_REFUNDS = 10
ESCALATION_CLEARED = 11
REREVIEW_CLEARED = 12
SUBMISSION = 13
DEVELOPER_COMMENT = 14
REVIEW_DEVICE_OVERRIDE = 15
REVIEW_FEATURES_OVERRIDE = 16
REREVIEW_MANIFEST_CHANGE = 17
REREVIEW_MANIFEST_URL_CHANGE = 18
REREVIEW_PREMIUM_TYPE_UPGRADE = 19
REREVIEW_DEVICES_ADDED = 20
REREVIEW_FEATURES_CHANGED = 21
REREVIEW_CONTENT_RATING_ADULT = 22
ESCALATION_VIP_APP = 22
ESCALATION_PRERELEASE_APP = 23
PRIORITY_REVIEW_REQUESTED = 24

NOTE_TYPES = {
    NO_ACTION: _('No action'),
    APPROVAL: _('Approved'),
    REJECTION: _('Rejected'),
    DISABLED: _('Disabled'),
    MORE_INFO_REQUIRED: _('More information requested'),
    ESCALATION: _('Escalated'),
    REVIEWER_COMMENT: _('Comment'),
    RESUBMISSION: _('App resubmission'),
    APPROVE_VERSION_WAITING: _('Approved but waiting to be made public'),
    ESCALATION_CLEARED: _('Escalation cleared'),
    ESCALATION_HIGH_ABUSE: _('Escalated due to High Abuse Reports'),
    ESCALATION_HIGH_REFUNDS: _('Escalated due to High Refund Requests'),
    REREVIEW_CLEARED: _('Re-review cleared'),
    SUBMISSION: _('App submission notes'),
    DEVELOPER_COMMENT: _('Developer comment'),
    REVIEW_DEVICE_OVERRIDE: _('Device(s) changed by reviewer'),
    REVIEW_FEATURES_OVERRIDE: _('Requirement(s) changed by reviewer'),
    REREVIEW_MANIFEST_CHANGE: _('Rereview due to Manifest Change'),
    REREVIEW_MANIFEST_URL_CHANGE: _('Rereview due to Manifest URL Change'),
    REREVIEW_PREMIUM_TYPE_UPGRADE: _('Rrereview due to Premium Type Upgrade'),
    REREVIEW_DEVICES_ADDED: _('Rereview due to Devices Added'),
    REREVIEW_FEATURES_CHANGED: _('Rereview due to Requirements Change'),
    REREVIEW_CONTENT_RATING_ADULT: _('Rereview due to Adult Content Rating'),
    ESCALATION_VIP_APP: _('Escalation due to VIP App'),
    ESCALATION_PRERELEASE_APP: _('Escalation due to Prelease App'),
    PRIORITY_REVIEW_REQUESTED: _('Priority review requested')
}

# Note types only visible by reviewers and not developers.
REVIEWER_NOTE_TYPES = (
    ESCALATION,
    REVIEWER_COMMENT,
    ESCALATION_HIGH_ABUSE,
    ESCALATION_HIGH_REFUNDS,
    ESCALATION_CLEARED,
    REREVIEW_MANIFEST_CHANGE,
    REREVIEW_MANIFEST_URL_CHANGE,
    REREVIEW_PREMIUM_TYPE_UPGRADE,
    REREVIEW_DEVICES_ADDED,
    REREVIEW_FEATURES_CHANGED,
    REREVIEW_CONTENT_RATING_ADULT,
    ESCALATION_VIP_APP,
    ESCALATION_PRERELEASE_APP,
    PRIORITY_REVIEW_REQUESTED
)

# Note types that can be created through the API view.
API_NOTE_TYPE_WHITELIST = (
    NO_ACTION,
    REVIEWER_COMMENT,
    DEVELOPER_COMMENT,
)


def U_NOTE_TYPES():
    return dict((key, unicode(value)) for (key, value) in
                NOTE_TYPES.iteritems())


def ACTION_MAP(activity_action):
    """Maps ActivityLog action ids to Commbadge note types."""
    import amo
    if isinstance(activity_action, amo._LOG):
        activity_action = activity_action.id

    return {
        amo.LOG.APPROVE_VERSION.id: APPROVAL,
        amo.LOG.APPROVE_VERSION_WAITING.id: APPROVE_VERSION_WAITING,
        amo.LOG.APP_DISABLED.id: DISABLED,
        amo.LOG.ESCALATE_MANUAL.id: ESCALATION,
        amo.LOG.ESCALATE_VERSION.id: ESCALATION,
        amo.LOG.ESCALATION_VIP_APP.id: ESCALATION,
        amo.LOG.ESCALATED_HIGH_ABUSE.id: ESCALATION_HIGH_ABUSE,
        amo.LOG.ESCALATED_HIGH_REFUNDS.id: ESCALATION_HIGH_REFUNDS,
        amo.LOG.ESCALATION_CLEARED.id: ESCALATION_CLEARED,
        amo.LOG.REQUEST_INFORMATION.id: MORE_INFO_REQUIRED,
        amo.LOG.REJECT_VERSION.id: REJECTION,
        amo.LOG.REREVIEW_CLEARED.id: REREVIEW_CLEARED,
        amo.LOG.WEBAPP_RESUBMIT.id: RESUBMISSION,
        amo.LOG.COMMENT_VERSION.id: REVIEWER_COMMENT,
        amo.LOG.REVIEW_FEATURES_OVERRIDE.id: REVIEW_FEATURES_OVERRIDE,
        amo.LOG.REVIEW_DEVICE_OVERRIDE.id: REVIEW_DEVICE_OVERRIDE,
        amo.LOG.REREVIEW_MANIFEST_CHANGE.id: REREVIEW_MANIFEST_CHANGE,
        amo.LOG.REREVIEW_MANIFEST_URL_CHANGE.id: REREVIEW_MANIFEST_URL_CHANGE,
        amo.LOG.REREVIEW_PREMIUM_TYPE_UPGRADE.id:
            REREVIEW_PREMIUM_TYPE_UPGRADE,
        amo.LOG.REREVIEW_DEVICES_ADDED.id: REREVIEW_DEVICES_ADDED,
        amo.LOG.REREVIEW_FEATURES_CHANGED.id: REREVIEW_FEATURES_CHANGED,
        amo.LOG.CONTENT_RATING_TO_ADULT.id:
            REREVIEW_CONTENT_RATING_ADULT,
        amo.LOG.ESCALATION_VIP_APP.id: ESCALATION_VIP_APP,
        amo.LOG.ESCALATION_PRERELEASE_APP.id: ESCALATION_PRERELEASE_APP,
        amo.LOG.PRIORITY_REVIEW_REQUESTED.id: PRIORITY_REVIEW_REQUESTED
    }.get(activity_action, NO_ACTION)


# Number of days a token is valid for.
THREAD_TOKEN_EXPIRY = 30

# Number of times a token can be used.
MAX_TOKEN_USE_COUNT = 5

MAX_ATTACH = 10

# Prefix of the reply to address in comm emails.
REPLY_TO_PREFIX = 'commreply+'
