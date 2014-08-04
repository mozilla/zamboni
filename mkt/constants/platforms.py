from tower import ugettext_lazy as _


class PLATFORM_ALL:
    id = 1
    name = _(u'All Platforms')
    shortname = 'all'
    api_name = u'ALL'


PLATFORMS = {PLATFORM_ALL.id: PLATFORM_ALL}


def FREE_PLATFORMS(request=None, is_packaged=False):
    import waffle
    platforms = (
        ('free-firefoxos', _('Firefox OS')),
    )

    android_packaged_enabled = (request and
        waffle.flag_is_active(request, 'android-packaged'))
    desktop_packaged_enabled = (request and
        waffle.flag_is_active(request, 'desktop-packaged'))

    if not is_packaged or (is_packaged and desktop_packaged_enabled):
        platforms += (
            ('free-desktop', _('Firefox for Desktop')),
        )

    if not is_packaged or (is_packaged and android_packaged_enabled):
        platforms += (
            ('free-android-mobile', _('Firefox Mobile')),
            ('free-android-tablet', _('Firefox Tablet')),
        )

    return platforms


def PAID_PLATFORMS(request=None, is_packaged=False):
    import waffle
    platforms = (
        ('paid-firefoxos', _('Firefox OS')),
    )

    android_payments_enabled = (request and
        waffle.flag_is_active(request, 'android-payments'))
    android_packaged_enabled = (request and
        waffle.flag_is_active(request, 'android-packaged'))

    if android_payments_enabled :
        if not is_packaged or (is_packaged and android_packaged_enabled):
            platforms += (
                ('paid-android-mobile', _('Firefox Mobile')),
                ('paid-android-tablet', _('Firefox Tablet')),
            )

    return platforms


# Extra information about those values for display in the page.
PLATFORMS_NAMES = {
    'free-firefoxos': _('Fully open mobile ecosystem'),
    'free-desktop': _('Windows, Mac and Linux'),
    'free-android-mobile': _('Android smartphones'),
    'free-android-tablet': _('Tablets'),
    'paid-firefoxos': _('Fully open mobile ecosystem'),
    'paid-android-mobile': _('Android smartphones'),
    'paid-android-tablet': _('Tablets'),
}
