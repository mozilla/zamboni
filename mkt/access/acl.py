import mkt


def match_rules(rules, app, action):
    """
    This will match rules found in Group.
    """
    for rule in rules.split(','):
        rule_app, rule_action = rule.split(':')
        if rule_app == '*' or rule_app == app:
            if (rule_action == '*' or
                    rule_action == action or
                    action == '%'):
                return True
    return False


def action_allowed(request, app, action):
    """
    Determines if the request user has permission to do a certain action

    'Admin:%' is true if the user has any of:
    ('Admin:*', 'Admin:%s'%whatever, '*:*',) as rules.
    """
    allowed = any(match_rules(group.rules, app, action) for group in
                  getattr(request, 'groups', ()))
    return allowed


def action_allowed_user(user, app, action):
    """Similar to action_allowed, but takes user instead of request."""
    allowed = any(match_rules(group.rules, app, action) for group in
                  user.groups.all())
    return allowed


def check_ownership(request, obj, require_owner=False, require_author=False,
                    ignore_disabled=False, admin=True):
    """
    A convenience function.  Check if request.user has permissions
    for the object.
    """
    if hasattr(obj, 'check_ownership'):
        return obj.check_ownership(request, require_owner=require_owner,
                                   require_author=require_author,
                                   ignore_disabled=ignore_disabled,
                                   admin=admin)
    return False


def check_addon_ownership(request, addon, viewer=False, dev=False,
                          support=False, admin=True, ignore_disabled=False):
    """
    Check request.user's permissions for the addon.

    If user is an admin they can do anything.
    If the app is disabled only admins have permission.
    If they're an app owner they can do anything.

    dev=True checks that the user has an owner or developer role.
    viewer=True checks that the user has an owner, developer, or viewer role.
    support=True checks that the user has a support role.
    """
    if not request.user.is_authenticated():
        return False
    # Deleted apps can't be edited at all.
    if addon.is_deleted:
        return False
    # Users with 'Apps:Edit' can do anything.
    if admin and action_allowed(request, 'Apps', 'Edit'):
        return True
    # Only admins can edit banned addons.
    if addon.status == mkt.STATUS_DISABLED and not ignore_disabled:
        return False
    # Addon owners can do everything else.
    roles = (mkt.AUTHOR_ROLE_OWNER,)
    if dev:
        roles += (mkt.AUTHOR_ROLE_DEV,)
    # Viewer privs are implied for devs.
    elif viewer:
        roles += (mkt.AUTHOR_ROLE_DEV, mkt.AUTHOR_ROLE_VIEWER,
                  mkt.AUTHOR_ROLE_SUPPORT)
    # Support can do support.
    elif support:
        roles += (mkt.AUTHOR_ROLE_SUPPORT,)
    return addon.authors.filter(pk=request.user.pk,
                                addonuser__role__in=roles).exists()


def check_reviewer(request, region=None):
    if region is not None:
        # This is for reviewers in special regions (e.g., China).
        from mkt.regions.utils import parse_region
        region_slug = parse_region(region).slug.upper()
        return action_allowed(request, 'Apps', 'ReviewRegion%s' % region_slug)

    return action_allowed(request, 'Apps', 'Review')
