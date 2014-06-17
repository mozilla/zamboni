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


DEVICE_TYPE_LIST = [DEVICE_DESKTOP, DEVICE_MOBILE, DEVICE_TABLET, DEVICE_GAIA]
DEVICE_TYPES = dict((d.id, d) for d in DEVICE_TYPE_LIST)
REVERSE_DEVICE_LOOKUP = dict((d.id, d.api_name) for d in DEVICE_TYPE_LIST)
DEVICE_LOOKUP = dict((d.api_name, d) for d in DEVICE_TYPE_LIST)
