import jinja2
from jingo import env, register

from tower import ungettext as ngettext

from amo.helpers import numberfmt

import mkt


@register.function
def platform_list(product):
    platforms = product.platforms
    if platforms:
        t = env.get_template('detail/helpers/platform_list.html')
        return jinja2.Markup(t.render({
            'platforms': platforms,
            'all_platforms': mkt.PLATFORM_TYPES.values()}))


@register.filter
def weekly_downloads(product):
    cnt = product.weekly_downloads
    return ngettext('{0} weekly download', '{0} weekly downloads',
                    cnt).format(numberfmt(cnt))
