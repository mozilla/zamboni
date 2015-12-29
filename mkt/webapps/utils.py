# -*- coding: utf-8 -*-
import hashlib
import json

from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured

import commonware.log
import waffle

import lib.iarc
import mkt
from mkt.site.storage_utils import public_storage
from mkt.site.utils import JSONEncoder
from mkt.translations.utils import find_language


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
    if waffle.switch_is_active('iarc-upgrade-v2'):
        raise ImproperlyConfigured(
            'We should not be calling this function with IARC v2.')

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


def get_cached_minifest(app_or_langpack, force=False):
    """
    Create a "mini" manifest for a packaged app or langpack and cache it (Call
    with `force=True` to bypass existing cache).

    Note that platform expects name/developer/locales to match the data from
    the real manifest in the package, so it needs to be read from the zip file.

    Returns a tuple with the minifest contents and the corresponding etag.
    """
    cache_prefix = 1  # Change this if you are modifying what enters the cache.
    cache_key = '{0}:{1}:{2}:manifest'.format(cache_prefix,
                                              app_or_langpack._meta.model_name,
                                              app_or_langpack.pk)

    if not force:
        cached_data = cache.get(cache_key)
        if cached_data:
            return cached_data

    sign_if_packaged = getattr(app_or_langpack, 'sign_if_packaged', None)
    if sign_if_packaged is None:
        # Langpacks are already signed when we generate the manifest and have
        # a file_path attribute.
        signed_file_path = app_or_langpack.file_path
    else:
        # sign_if_packaged() will return the signed path. But to call it, we
        # need a current version. If we don't have one, return an empty
        # manifest, bypassing caching so that when a version does become
        # available it can get picked up correctly.
        if not app_or_langpack.current_version:
            return '{}'
        signed_file_path = sign_if_packaged()

    manifest = app_or_langpack.get_manifest_json()
    package_path = app_or_langpack.get_package_path()

    data = {
        'size': public_storage.size(signed_file_path),
        'package_path': package_path,
    }
    if hasattr(app_or_langpack, 'current_version'):
        data['version'] = app_or_langpack.current_version.version
        data['release_notes'] = app_or_langpack.current_version.releasenotes
        file_hash = app_or_langpack.current_version.all_files[0].hash
    else:
        # LangPacks have no version model, the version number is an attribute
        # and they don't have release notes.
        data['version'] = app_or_langpack.version
        # File hash is not stored for langpacks, but file_version changes with
        # every new upload so we can use that instead.
        file_hash = unicode(app_or_langpack.file_version)

    for key in ['developer', 'icons', 'locales', 'name']:
        if key in manifest:
            data[key] = manifest[key]

    data = json.dumps(data, cls=JSONEncoder)
    etag = hashlib.sha256()
    etag.update(data)
    if file_hash:
        etag.update(file_hash)
    rval = (data, etag.hexdigest())
    cache.set(cache_key, rval, None)
    return rval
