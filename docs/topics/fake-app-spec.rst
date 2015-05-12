.. _fake-app-spec:

===============
 Fake App Data
===============

The `generate_apps_from_spec` command-line tool loads a JSON file containing an
array of fake app objects. The fields that can be specified in these objects
are:

type
    Required. One of "hosted", "web", or "privileged", to specify a hosted app,
    unprivileged packaged app, or privileged packaged app.

status
    Required. A string representing the app status, as listed in
    ``mkt.constants.base.STATUS_CHOICES_API``.

name
    The display name for the app.

num_ratings
    Number of user ratings to create for this app.

num_previews
    Number of screenshots to create for this app.

preview_files
    List of paths (relative to the JSON file) of preview images.

video_files
    List of paths (relative to the JSON file) of preview videos in webm format.

num_locales
    Number of locales to localize this app's name in (max 5).

versions
    An array of objects with optional version-specific fields: "status",
    "type", and "permissions". Additional versions with these fields are
    created, oldest first.

permissions
    An array of app permissions, to be placed in the manifest.

manifest_file
    Path (relative to the JSON file) of a manifest to create this app from.

description
    Description text for the app.

categories
    A list of category names to create the app in.

developer_name
    Display name for the app author.

developer_email
    An email address for the app author.

device_types
    A list of devices the app is available on: one or more of "desktop", "mobile", "tablet", and "firefoxos".

premium_type
    Payment status for the app. One of "free", "premium", "premium-inapp", "free-inapp", or "other".

price
    The price (in dollars) for the app.

privacy_policy
    Privacy policy text.

rereview
    Boolean indicating whether to place app in rereview queue.

special_regions
    An object with region names as keys, and status strings as values. Adds app to special
    region with given status.
