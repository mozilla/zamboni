import jingo
from tower import ugettext as _

from mkt.access import acl


@jingo.register.filter
def stars(num, large=False):
    # check for 0.0 incase None was cast to a float. Should
    # be safe since lowest rating you can give is 1.0
    if num is None or num == 0.0:
        return _('Not yet reviewed')
    else:
        num = min(5, int(round(num)))
        return _('Reviewed %s out of 5 stars' % num)


def user_can_delete_review(request, review):
    """Return whether or not the request.user can delete reviews.

    People who can delete reviews:
      * The original review author.
      * Reviewers, but only if they aren't listed as an author of the add-on.
      * Users in a group with "Users:Edit" privileges.
      * Users in a group with "Apps:ModerateReview" privileges.

    """
    is_editor = acl.check_reviewer(request)
    is_author = review.addon.has_author(request.user)
    return (
        review.user_id == request.user.id or
        not is_author and (
            is_editor or
            acl.action_allowed(request, 'Users', 'Edit') or
            acl.action_allowed(request, 'Apps', 'ModerateReview')))
