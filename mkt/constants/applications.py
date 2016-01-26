from tower import ugettext_lazy as _


class DEVICE_DESKTOP(object):
    id = 1
    name = _(u'Desktop')
    class_name = 'desktop'
    api_name = 'desktop'


class DEVICE_MOBILE(object):
    id = 2
    name = _(u'Firefox Mobile')
    class_name = 'android-mobile'
    api_name = 'android-mobile'


class DEVICE_TABLET(object):
    id = 3
    name = _(u'Firefox Tablet')
    class_name = 'android-tablet'
    api_name = 'android-tablet'


class DEVICE_GAIA(object):
    id = 4
    name = _(u'Firefox OS')
    class_name = 'firefoxos'
    api_name = 'firefoxos'


class DEVICE_TV(object):
    id = 5
    name = _(u'Firefox OS TV')
    class_name = 'firefoxos-tv'
    api_name = 'firefoxos-tv'


DEVICE_TYPE_LIST = [DEVICE_DESKTOP, DEVICE_MOBILE, DEVICE_TABLET, DEVICE_GAIA,
                    DEVICE_TV]
DEVICE_TYPES = dict((d.id, d) for d in DEVICE_TYPE_LIST)
VISIBLE_DEVICE_TYPES = dict((k, v) for k, v in DEVICE_TYPES.iteritems()
                            if v is not DEVICE_TV)
REVERSE_DEVICE_LOOKUP = dict((d.id, d.api_name) for d in DEVICE_TYPE_LIST)
DEVICE_LOOKUP = dict((d.api_name, d) for d in DEVICE_TYPE_LIST)
DEVICE_CHOICES = ((d.id, d.name) for d in DEVICE_TYPE_LIST)

# For search and feed.
DEVICE_CHOICES_IDS = {
    'desktop': DEVICE_DESKTOP.id,
    'mobile': DEVICE_MOBILE.id,
    'tablet': DEVICE_TABLET.id,
    'firefoxos': DEVICE_GAIA.id,
    'firefoxos-tv': DEVICE_TV.id,
}


def get_device(request):
    # Fireplace sends `dev` and `device`. See the API docs. When `dev` is
    # 'android' we also need to check `device` to pick a device object.
    dev = request.GET.get('dev')
    device = request.GET.get('device')

    if dev == 'android' and device:
        dev = '%s-%s' % (dev, device)

    return DEVICE_LOOKUP.get(dev)


def get_device_id(request):
    return getattr(get_device(request), 'id', None)
