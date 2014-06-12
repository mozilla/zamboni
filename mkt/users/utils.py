import uuid
from functools import partial

from django.conf import settings

import commonware.log

from mkt.users.models import UserProfile


log = commonware.log.getLogger('z.users')


def get_task_user():
    """
    Returns a user object. This user is suitable for assigning to
    cron jobs or long running tasks.
    """
    return UserProfile.objects.get(pk=settings.TASK_USER_ID)


def autocreate_username(candidate, tries=1):
    """Returns a unique valid username."""
    max_tries = settings.MAX_GEN_USERNAME_TRIES
    from amo.utils import slugify, SLUG_OK
    make_u = partial(slugify, ok=SLUG_OK, lower=True, spaces=False,
                     delimiter='-')
    adjusted_u = make_u(candidate)
    if tries > 1:
        adjusted_u = '%s%s' % (adjusted_u, tries)
    if (adjusted_u == '' or tries > max_tries or len(adjusted_u) > 255):
        log.info('username empty, max tries reached, or too long;'
                 ' username=%s; max=%s' % (adjusted_u, max_tries))
        return autocreate_username(uuid.uuid4().hex[0:15])
    if UserProfile.objects.filter(username=adjusted_u).count():
        return autocreate_username(candidate, tries=tries + 1)
    return adjusted_u
