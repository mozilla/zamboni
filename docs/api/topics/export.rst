.. _export:

======
Export
======

There is an export of nightly data that is available as a tarball. The download
can be found at the following URLs (replace YYYY-MM-DD with today's date):

* Development server: https://marketplace-dev-cdn.allizom.org/dumped-apps/tarballs/YYYY-MM-DD.tgz

* Production server: https://marketplace.cdn.mozilla.net/dumped-apps/tarballs/YYYY-MM-DD.tgz

Files remain on the server for 30 days then are removed.

Contents:

* *readme.txt* and *license.txt*: information about the export.

* *apps*: this directory contains all the exported apps. Each app is a separate
  JSON file and contains the output of :ref:`the app GET method <app-response-label>`.

* *collections*: this directory contains all the exported collections. Each
  collection is a separate JSON file with the format shown below.

-----------------
Collection Format
-----------------

The collection format lists the collection data and references to the apps
within the collection. The app data is just an ID and filepath.

.. warning:: Ensure that you only read files within your export directory by
             expanding the filepath (parts like ../ and /) and verifying the
             computed path.

Example:

.. code-block:: json

    {
        "apps": [
            {
                "filepath": "apps/444/444002.json",
                "pk": 444002
            },
            {
                "filepath": "apps/432/432512.json",
                "pk": 432512
            }
        ],
        "author": "Me",
        "background_color": "#543210",
        "carrier": null,
        "category": null,
        "collection_type": 0,
        "default_language": "en-US",
        "description": {
            "en-US": "My favourite apps."
        },
        "id": 73,
        "image": "https://img-domain.com/path/to/image.png",
        "is_public": true,
        "name": {
            "en-US": "My Apps"
        },
        "region": null,
        "slug": "my-apps",
        "text_color": "#012345"
    }

Caveats:

* Apps and collections must be public to be exported, which means records may
  be removed as their status on the marketplace changes.

* No user object is present, so user specific information about the app is not
  present.

* The export has no locale, region or carrier specified. It defaults to the
  region ``restofworld`` and locale ``en-US``.
