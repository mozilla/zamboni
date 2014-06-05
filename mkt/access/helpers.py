import jinja2
from jingo import register

import acl


@register.function
@jinja2.contextfunction
def action_allowed(context, app, action):
    return acl.action_allowed(context['request'], app, action)
