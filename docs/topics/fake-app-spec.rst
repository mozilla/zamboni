.. _fake-app-spec:

===============
 Fake App Data
===============

The `generate_apps_from_spec` command-line tool loads a JSON file containing an
array of fake app objects. The fields that can be specified in these objects
are:

type
    One of "hosted", "web", or "privileged", to specify a hosted app,
    unprivileged packaged app, or privileged packaged app.

status
    An string representing the app status, as listed in
    ``mkt.constants.base.STATUS_CHOICES_API``.

num_ratings
    Number of user ratings to create for this app.

num_previews
    Number of screenshots to create for this app.

num_locales
    Number of locales to localize this app's name in (max 5).

versions
    An array of integers representing version statuses; a version with each
    status will be created, oldest first. (Not applicable to hosted apps.)

permissions
    An array of app permissions, to be placed in the manifest.

