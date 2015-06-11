from tower import ugettext_lazy as _


# To add a note type:
# - assign it a incremented number (MY_NOTE_TYPE = 42)
# - give it a translation in NOTE_TYPES
# - if adding from mkt/site/log.py, add it to ACTION_MAP
# - add it to REVIEWERS_NOTE_TYPE if it should only be visible to reviewers
# - add the translation to Commbadge settings

NO_ACTION = 0
APPROVAL = 1
REJECTION = 2
DISABLED = 3
MORE_INFO_REQUIRED = 4
ESCALATION = 5
REVIEWER_COMMENT = 6
RESUBMISSION = 7
APPROVE_VERSION_PRIVATE = 8
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
ESCALATION_VIP_APP = 22
ESCALATION_PRERELEASE_APP = 23
PRIORITY_REVIEW_REQUESTED = 24
ADDITIONAL_REVIEW_PASSED = 25
ADDITIONAL_REVIEW_FAILED = 26
DEVELOPER_VERSION_NOTE_FOR_REVIEWER = 27
REVIEWER_PUBLIC_COMMENT = 28
REREVIEW_CONTENT_RATING_ADULT = 29
REREVIEW_ABUSE_APP = 30

NOTE_TYPES = {
    NO_ACTION: _('No action'),
    APPROVAL: _('Approved'),
    REJECTION: _('Rejected'),
    DISABLED: _('Banned'),
    MORE_INFO_REQUIRED: _('Reviewer comment'),
    ESCALATION: _('Escalated'),
    REVIEWER_COMMENT: _('Private reviewer comment'),
    RESUBMISSION: _('App resubmission'),
    APPROVE_VERSION_PRIVATE: _('Approved but private'),
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
    REREVIEW_PREMIUM_TYPE_UPGRADE: _('Rereview due to Premium Type Upgrade'),
    REREVIEW_DEVICES_ADDED: _('Rereview due to Devices Added'),
    REREVIEW_FEATURES_CHANGED: _('Rereview due to Requirements Change'),
    REREVIEW_CONTENT_RATING_ADULT: _('Rereview due to Adult Content Rating'),
    ESCALATION_VIP_APP: _('Escalation due to VIP App'),
    ESCALATION_PRERELEASE_APP: _('Escalation due to Prelease App'),
    PRIORITY_REVIEW_REQUESTED: _('Priority review requested'),
    ADDITIONAL_REVIEW_PASSED: _('Additional review passed'),
    ADDITIONAL_REVIEW_FAILED: _('Additional review failed'),
    DEVELOPER_VERSION_NOTE_FOR_REVIEWER: _('Version notes for reviewer'),
    REVIEWER_PUBLIC_COMMENT: _('Public reviewer comment'),
    REREVIEW_ABUSE_APP: _('Abuse reports investigation'),
}

# Note types only visible by reviewers and not developers.
# These will set read_permission_developer on notes to False.
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
    REREVIEW_CLEARED,
    ESCALATION_VIP_APP,
    ESCALATION_PRERELEASE_APP,
    PRIORITY_REVIEW_REQUESTED,
    REREVIEW_ABUSE_APP,
)

# Note types that can be created through the API view.
API_NOTE_TYPE_ALLOWED = (
    NO_ACTION,
    REVIEWER_COMMENT,
    DEVELOPER_COMMENT,
    REVIEWER_PUBLIC_COMMENT
)

# Maps from note type to email template names.
# Note types not listed will default to the 'generic' email.
COMM_MAIL_MAP = {
    APPROVAL: 'approval',
    REJECTION: 'rejection',
    DISABLED: 'disabled',
    MORE_INFO_REQUIRED: 'more_info_required',
    APPROVE_VERSION_PRIVATE: 'approval_private',
    ESCALATION_VIP_APP: 'escalation_vip',
    ESCALATION_PRERELEASE_APP: 'escalation_prerelease_app',
    ADDITIONAL_REVIEW_PASSED: 'tarako',
    ADDITIONAL_REVIEW_FAILED: 'tarako',
}

# Note types to only email senior reviewers on.
EMAIL_SENIOR_REVIEWERS = [
    ESCALATION_VIP_APP,
    ESCALATION_PRERELEASE_APP,
]

# Note types to email both senior reviewers and developer, but a different
# email template to each one.
EMAIL_SENIOR_REVIEWERS_AND_DEV = {
    ESCALATION: {
        'reviewer': 'escalation_senior_reviewer',
        'developer': 'escalation_developer',
    }
}


def U_NOTE_TYPES():
    return dict((key, unicode(value)) for (key, value) in
                NOTE_TYPES.iteritems())


def ACTION_MAP(activity_action):
    """Maps ActivityLog action ids to Commbadge note types."""
    import mkt
    if not isinstance(activity_action, int) and hasattr(activity_action, 'id'):
        activity_action = activity_action.id

    return {
        mkt.LOG.APPROVE_VERSION.id: APPROVAL,
        mkt.LOG.APPROVE_VERSION_PRIVATE.id: APPROVE_VERSION_PRIVATE,
        mkt.LOG.APP_DISABLED.id: DISABLED,
        mkt.LOG.ESCALATE_MANUAL.id: ESCALATION,
        mkt.LOG.ESCALATE_VERSION.id: ESCALATION,
        mkt.LOG.ESCALATION_VIP_APP.id: ESCALATION,
        mkt.LOG.ESCALATED_HIGH_ABUSE.id: ESCALATION_HIGH_ABUSE,
        mkt.LOG.ESCALATED_HIGH_REFUNDS.id: ESCALATION_HIGH_REFUNDS,
        mkt.LOG.ESCALATION_CLEARED.id: ESCALATION_CLEARED,
        mkt.LOG.REQUEST_INFORMATION.id: MORE_INFO_REQUIRED,
        mkt.LOG.REJECT_VERSION.id: REJECTION,
        mkt.LOG.REREVIEW_CLEARED.id: REREVIEW_CLEARED,
        mkt.LOG.WEBAPP_RESUBMIT.id: RESUBMISSION,
        mkt.LOG.COMMENT_VERSION.id: REVIEWER_COMMENT,
        mkt.LOG.REVIEW_FEATURES_OVERRIDE.id: REVIEW_FEATURES_OVERRIDE,
        mkt.LOG.REVIEW_DEVICE_OVERRIDE.id: REVIEW_DEVICE_OVERRIDE,
        mkt.LOG.REREVIEW_MANIFEST_CHANGE.id: REREVIEW_MANIFEST_CHANGE,
        mkt.LOG.REREVIEW_MANIFEST_URL_CHANGE.id: REREVIEW_MANIFEST_URL_CHANGE,
        mkt.LOG.REREVIEW_PREMIUM_TYPE_UPGRADE.id:
            REREVIEW_PREMIUM_TYPE_UPGRADE,
        mkt.LOG.REREVIEW_DEVICES_ADDED.id: REREVIEW_DEVICES_ADDED,
        mkt.LOG.REREVIEW_FEATURES_CHANGED.id: REREVIEW_FEATURES_CHANGED,
        mkt.LOG.CONTENT_RATING_TO_ADULT.id:
            REREVIEW_CONTENT_RATING_ADULT,
        mkt.LOG.ESCALATION_VIP_APP.id: ESCALATION_VIP_APP,
        mkt.LOG.ESCALATION_PRERELEASE_APP.id: ESCALATION_PRERELEASE_APP,
        mkt.LOG.PRIORITY_REVIEW_REQUESTED.id: PRIORITY_REVIEW_REQUESTED,
        mkt.LOG.PASS_ADDITIONAL_REVIEW.id: ADDITIONAL_REVIEW_PASSED,
        mkt.LOG.FAIL_ADDITIONAL_REVIEW.id: ADDITIONAL_REVIEW_FAILED,
        mkt.LOG.REREVIEW_ABUSE_APP.id: REREVIEW_ABUSE_APP,
    }.get(activity_action, NO_ACTION)


# Number of days a token is valid for.
THREAD_TOKEN_EXPIRY = 30

# Number of times a token can be used.
MAX_TOKEN_USE_COUNT = 5

MAX_ATTACH = 10

# Prefix of the reply to address in comm emails.
REPLY_TO_PREFIX = 'commreply+'
