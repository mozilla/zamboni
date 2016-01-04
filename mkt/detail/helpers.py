import jinja2
from jingo import register

from mkt.constants.applications import DEVICE_TYPES
from mkt.site.utils import env


@register.function
def device_list(product):
    device_types = product.device_types
    if device_types:
        t = env.get_template('detail/helpers/device_list.html')
        return jinja2.Markup(t.render({
            'device_types': device_types,
            'all_device_types': DEVICE_TYPES.values()}))


@register.function
def device_list_es(product):
    device_types = [DEVICE_TYPES[id] for id in product.device]
    t = env.get_template('detail/helpers/device_list.html')
    return jinja2.Markup(t.render({
        'device_types': device_types,
        'all_device_types': DEVICE_TYPES.values()}))
