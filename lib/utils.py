from urlparse import urljoin

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def validate_settings():
    """
    Validate that if not in DEBUG mode, key settings have been changed.
    """
    if settings.DEBUG or settings.IN_TEST_SUITE:
        return

    # Things that values must not be.
    for key, value in [
            ('SECRET_KEY', 'please change this'),
            ('SESSION_COOKIE_SECURE', False),
            ('APP_PURCHASE_SECRET', 'please change this')]:
        if getattr(settings, key) == value:
            raise ImproperlyConfigured('{0} must be changed from default'
                                       .format(key))


def static_url(url):
    """
    Return the relevant URL from settings. Rather than rely on
    a complicated layer of settings to do their work, this just does
    it at runtime. This allows MEDIA_URL, STATIC_URL and VAMO_URL to be
    changed in a local settings file, without having to overidde all the
    URLs.

    If the URL starts with https:// or http://, then no changes are made.
    """
    prefix = {
        'ADDON_ICONS_DEFAULT_URL': settings.MEDIA_URL,
        'ADDON_ICON_URL': settings.STATIC_URL,
        'PREVIEW_THUMBNAIL_URL': settings.STATIC_URL,
        'PREVIEW_FULL_URL': settings.STATIC_URL,
        'PRODUCT_ICON_URL': settings.MEDIA_URL,
        'WEBAPPS_RECEIPT_URL': settings.SITE_URL
    }

    value = getattr(settings, url)
    if value.startswith(('https://', 'http://')):
        return value
    if settings.DEBUG and settings.SERVE_TMP_PATH:
        return urljoin(prefix[url], '/tmp' + value)
    return urljoin(prefix[url], value)
