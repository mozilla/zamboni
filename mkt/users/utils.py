import datetime

from django.conf import settings
from django.db import transaction

import commonware.log

import mkt

from mkt.access.models import Group, GroupUser
from mkt.api.models import Access
from mkt.users.models import UserProfile


log = commonware.log.getLogger('z.users')


def get_task_user():
    """
    Returns a user object. This user is suitable for assigning to
    cron jobs or long running tasks.
    """
    return UserProfile.objects.get(pk=settings.TASK_USER_ID)


@transaction.atomic
def create_user(email, group_name=None, overwrite=False,
                oauth_key=None, oauth_secret=None):
    """Create an user if he doesn't exist already, assign him to a group and
    create a token for him.

    if ``overwrite=True`` then existing OAuth credentials for this user will be
    deleted, if any.

    If OAuth credentials are not specified, random key and secret will be
    generated.

    """
    # Create the user.
    profile, created = UserProfile.objects.get_or_create(
        email=email, source=mkt.LOGIN_SOURCE_UNKNOWN,
        display_name=email)

    if not profile.read_dev_agreement:
        profile.read_dev_agreement = datetime.datetime.now()
        profile.save()

    # Now, find the group we want.
    if (group_name and not profile.groups.filter(
            groupuser__group__name=group_name).exists()):
        group = Group.objects.get(name=group_name)
        GroupUser.objects.create(group=group, user=profile)

    if overwrite:
        Access.objects.filter(user=profile.user).delete()

    if not Access.objects.filter(user=profile).exists():
        if oauth_key and oauth_secret:
            Access.objects.create(user=profile, key=oauth_key,
                                  secret=oauth_secret)
        else:
            if oauth_key or oauth_secret:
                raise ValueError("Specify both of oauth_key and oauth_secret, "
                                 "or neither")
            Access.create_for_user(profile)
    return profile
