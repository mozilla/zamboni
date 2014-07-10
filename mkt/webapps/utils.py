# -*- coding: utf-8 -*-
import commonware.log

from amo.utils import find_language
import lib.iarc

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


def iarc_get_app_info(app):
    client = lib.iarc.client.get_iarc_client('services')
    iarc = app.iarc_info
    iarc_id = iarc.submission_id
    iarc_code = iarc.security_code

    # Generate XML.
    xml = lib.iarc.utils.render_xml(
        'get_app_info.xml',
        {'submission_id': iarc_id, 'security_code': iarc_code})

    # Process that shizzle.
    resp = client.Get_App_Info(XMLString=xml)

    # Handle response.
    return lib.iarc.utils.IARC_XML_Parser().parse_string(resp)
