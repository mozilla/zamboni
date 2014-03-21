from tower import ugettext_lazy as _lazy

from constants.applications import (DEVICE_DESKTOP, DEVICE_GAIA, DEVICE_MOBILE,
                                    DEVICE_TABLET)


class PLATFORM_DESKTOP(object):
    id = 1
    name = _lazy(u'Desktop')
    slug = 'desktop'


class PLATFORM_ANDROID(object):
    id = 2
    name = _lazy(u'Android')
    slug = 'android'


class PLATFORM_FXOS(object):
    id = 3
    name = _lazy(u'Firefox OS')
    slug = 'firefoxos'


PLATFORM_LIST = [PLATFORM_DESKTOP, PLATFORM_ANDROID, PLATFORM_FXOS]
PLATFORM_TYPES = dict((d.id, d) for d in PLATFORM_LIST)
REVERSE_PLATFORM_LOOKUP = dict((d.id, d.slug) for d in PLATFORM_LIST)
PLATFORM_LOOKUP = dict((d.slug, d) for d in PLATFORM_LIST)


def FREE_PLATFORMS(request=None, is_packaged=False):
    import waffle
    platforms = (
        ('free-firefoxos', _lazy('Firefox OS')),
    )

    android_packaged_enabled = (request and
        waffle.flag_is_active(request, 'android-packaged'))
    desktop_packaged_enabled = (request and
        waffle.flag_is_active(request, 'desktop-packaged'))

    if not is_packaged or (is_packaged and desktop_packaged_enabled):
        platforms += (
            ('free-desktop', _lazy('Firefox for Desktop')),
        )

    if not is_packaged or (is_packaged and android_packaged_enabled):
        platforms += (
            ('free-android', _lazy('Android')),
        )

    return platforms


def PAID_PLATFORMS(request=None, is_packaged=False):
    import waffle
    platforms = (
        ('paid-firefoxos', _lazy('Firefox OS')),
    )

    android_payments_enabled = (request and
        waffle.flag_is_active(request, 'android-payments'))
    android_packaged_enabled = (request and
        waffle.flag_is_active(request, 'android-packaged'))

    if android_payments_enabled:
        if not is_packaged or (is_packaged and android_packaged_enabled):
            platforms += (
                ('paid-android', _lazy('Android')),
            )

    return platforms


# Extra information about those values for display in the page.
PLATFORM_SUMMARIES = {
    'free-firefoxos': _lazy('Fully open mobile ecosystem'),
    'free-desktop': _lazy('Windows, Mac and Linux'),
    'free-android': _lazy('Devices running Android'),
    'paid-firefoxos': _lazy('Fully open mobile ecosystem'),
    'paid-android': _lazy('Devices running Android'),
}


# Mapping from old device types to platforms. Used as a compatibility layer to
# avoid breaking the API.
DEVICE_TO_PLATFORM = {
    DEVICE_DESKTOP.id: PLATFORM_DESKTOP,
    DEVICE_MOBILE.id: PLATFORM_ANDROID,
    DEVICE_TABLET.id: PLATFORM_ANDROID,
    DEVICE_GAIA.id: PLATFORM_FXOS,
}
