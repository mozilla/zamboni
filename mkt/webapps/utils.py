# -*- coding: utf-8 -*-
from collections import defaultdict

import commonware.log

import amo
from amo.utils import find_language

import mkt

log = commonware.log.getLogger('z.webapps')


def get_locale_properties(manifest, property, default_locale=None):
    locale_dict = {}
    for locale in manifest.get('locales', {}):
        if property in manifest['locales'][locale]:
            locale_dict[locale] = manifest['locales'][locale][property]

    # Add in the default locale name.
    default = manifest.get('default_locale') or default_locale
    root_property = manifest.get(property)
    if default and root_property:
        locale_dict[default] = root_property

    return locale_dict


def get_supported_locales(manifest):
    """
    Returns a list of locales found in the "locales" property of the manifest.

    This will convert locales found in the SHORTER_LANGUAGES setting to their
    full locale. It will also remove locales not found in AMO_LANGUAGES.

    Note: The default_locale is not included.

    """
    return sorted(filter(None, map(find_language, set(
        manifest.get('locales', {}).keys()))))


def dehydrate_content_rating(rating):
    """
    {body.id, rating.id} to translated rating.label.
    """
    try:
        body = mkt.ratingsbodies.dehydrate_ratings_body(
            mkt.ratingsbodies.RATINGS_BODIES[int(rating['body'])])
    except TypeError:
        # Legacy ES format (bug 943371).
        return {}

    rating = mkt.ratingsbodies.dehydrate_rating(
        body.ratings[int(rating['rating'])])

    return rating.label


def dehydrate_content_ratings(content_ratings):
    """Dehydrate an object of content ratings from rating IDs to dict."""
    for body in content_ratings or {}:
        # Dehydrate all content ratings.
        content_ratings[body] = dehydrate_content_rating(content_ratings[body])
    return content_ratings


def dehydrate_descriptors(keys, body=None):
    """
    List of keys to lists of objects (desc label, desc name) by body.

    ['ESRB_BLOOD, ...] to {'esrb': ['blood'], ...}.
    """
    results = defaultdict(list)
    for key in keys:
        obj = mkt.ratingdescriptors.RATING_DESCS.get(key)
        if obj:
            # Slugify and remove body prefix.
            body, label = key.lower().replace('_', '-').split('-', 1)
            results[body].append(label)
    return dict(results)


def dehydrate_interactives(keys):
    """
    List of keys to list of objects (label, name).

    ['SOCIAL_NETWORKING', ...] to ['social-networking', ...].
    """
    results = []
    for key in keys:
        obj = mkt.ratinginteractives.RATING_INTERACTIVES.get(key)
        if obj:
            results.append(key.lower().replace('_', '-'))
    return results


def get_device_types(platforms, form_factors):
    """
    Given a list of platform and form_factor objects, returns the device types.

    This is used to help maintain compatibility with API v1.
    """
    device_types = []

    if mkt.PLATFORM_DESKTOP in platforms:
        device_types.append(amo.DEVICE_DESKTOP)
    if mkt.PLATFORM_FXOS in platforms:
        device_types.append(amo.DEVICE_GAIA)
    if mkt.PLATFORM_ANDROID in platforms:
        if mkt.FORM_MOBILE in form_factors:
            device_types.append(amo.DEVICE_MOBILE)
        if mkt.FORM_TABLET in form_factors:
            device_types.append(amo.DEVICE_TABLET)

    return device_types
