import uuid

from django.conf import settings

import jinja2
from jingo import register
from jingo.helpers import urlparams

from mkt.account.views import fxa_oauth_api


@jinja2.contextfunction
@register.function
def fxa_auth_info(context=None):
    state = uuid.uuid4().hex
    return (state,
            urlparams(
                fxa_oauth_api('authorization'),
                client_id=settings.FXA_CLIENT_ID,
                state=state,
                scope='profile'))
