from tower import ugettext_lazy as _


def FREE_PLATFORMS():
    platforms = (
        ('free-firefoxos', _('Firefox OS')),
        ('free-desktop', _('Firefox for Desktop')),
        ('free-android-mobile', _('Firefox Mobile')),
        ('free-android-tablet', _('Firefox Tablet')),
    )

    return platforms


def PAID_PLATFORMS(request=None):
    import waffle
    platforms = (
        ('paid-firefoxos', _('Firefox OS')),
    )

    active = waffle.flag_is_active
    android_pay = request and active(request, 'android-payments')
    desktop_pay = request and active(request, 'desktop-payments')

    if desktop_pay:
        platforms += (
            ('paid-desktop', _('Firefox for Desktop')),
        )

    if android_pay:
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
    'paid-desktop': _('Windows, Mac and Linux'),
    'paid-android-mobile': _('Android smartphones'),
    'paid-android-tablet': _('Tablets'),
}
