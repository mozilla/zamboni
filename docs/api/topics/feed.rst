.. _feed:
.. versionadded:: 2

====
Feed
====

The feed is a stream of content relevant to the user displayed on
the Marketplace home page. The feed is comprised of a number of :ref:`feed items
<feed-items>`, each containing a singular of piece of content. Currently, the
feed may include:

- :ref:`Feed Apps <feed-apps>`
- :ref:`Feed Brands <feed-brands>`
- :ref:`Feed Collections <feed-collections>`
- :ref:`Operator Shelves <feed-shelves>`

.. note::

    ``GET``, ``HEAD``, and ``OPTIONS`` requests to these endpoints may be made
    anonymously. Authentication and the ``Feed:Curate`` permission are required
    to make any other request.

.. note::

    New in version 2 of the API.

.. _feed-feed:

----
Feed
----

.. http:get:: /api/v2/feed/get/?carrier=(str:carrier)&region=(str:region)

    A convenience endpoint containing all the data necessary for a user's feed,
    which currently includes:

    - All the :ref:`feed items <feed-items>`.

    If an operator shelf is available for the passed in carrier + region, it
    appear first in the list of feed items in the respnse.


    **Request**

    :param carrier: the slug of a :ref:`carrier <carriers>`. Omit if no carrier
        is available.
    :type carrier: str
    :param region: the slug of a :ref:`region <regions>`. Omit if no region is
        available.
    :type region: str


    **Response**

    :param meta: :ref:`meta-response-label`.
    :type meta: object
    :param objects: An ordered list of :ref:`feed items <feed-items>` for the
        user.
    :type objects: array

    .. code-block:: json

        {
            "objects": [
                {
                    "id": 343,
                    ...
                },
                {
                    "id": 518,
                    ...
                }
            ],
        }


.. _feed-items:

----------
Feed Items
----------

A feed item wraps a :ref:`feed app  <feed-apps>`, :ref:`feed brand
<feed-brands>`, or :ref:`feed collection <feed-collections>` with additional
metadata regarding when and where to feature the content. Feed items are
represented thusly:

.. code-block:: json

    {
        "app": null,
        "brand": null,
        "carrier": "telefonica",
        "collection": {
            "data": "..."
        }
        "id": 47,
        "item_type": "collection",
        "region": "br",
        "resource_url": "/api/v2/feed/items/47/",
        "shelf": null
    }

``app``
    *object|null* - the full representation of a :ref:`feed app <feed-apps>`.
``brand``
    *object|null* - the full representation of a :ref:`feed brand
    <feed-brands>`.
``carrier``
    *string|null* - the slug of a :ref:`carrier <carriers>`. If
    defined, this feed item will only be available by users of that carrier.
``category``
    *string|null* - the slug of a :ref:`category <categories>`. If defined,
    this feed item will only be available to users browsing that category.
``collection``
    *object|null* - the full representation of a  :ref:`collection
    <collections>`.
``id``
    *int* the ID of this feed item.
``item_type``
    *string* - the type of object being represented by this feed item. This
    will always be usable as a key on the feed item instance to fetch that
    object's data (i.e. ``feeditem[feeditem['item_type']]`` will always be
    non-null). Can be ``app``, ``collection``, or ``brand``.
``order``
    *int* - order/weight at which the feed item is displayed on a feed.
``resource_url``
    *string* - the permanent URL for this feed item.
``region``
    *string|null* - the slug of a :ref:`region <regions>`. If defined, this
    feed item will only be available in that region.
``shelf``
    *object* - the full representation of an :ref:`operator shelf
    <feed-shelves>`.


List
====

.. http:get:: /api/v2/feed/items/

    A listing of feed items.

    **Response**

    :param feed: :ref:`meta-response-label`.
    :type feed: object
    :param shelf: A :ref:`listing <objects-response-label>` of
        :ref:`feed items <feed-items>`.
    :type shelf: array

    .. code-block:: json

        {
            "carrier": null,
            "category": null,
            "collection": 4,
            "region": 1
        }


Detail
======

.. http:get:: /api/v2/feed/items/(int:id)/

    Detail of a specific feed item.

    **Request**

    :param id: the ID of the feed item.
    :type id: int

    **Response**

    A representation of the :ref:`feed item <feed-items>`.


Create
======

.. http:post:: /api/v2/feed/items/

    Create a feed item.

    **Request**

    :param carrier: the ID of a :ref:`carrier <carriers>`. If defined, it will
        restrict this feed item to only be viewed by users of this carrier.
    :type carrier: int|null
    :param category: the slug of a :ref:`category <categories>`. If defined,
        it will restrict this feed item to only be viewed by users browsing
        this category.
    :type category: string|null
    :param region: the ID of a :ref:`region <regions>`. If defined, it will
        restrict this feed item to only be viewed in this region.
    :type region: int|null

    The following parameters define the object contained by this feed item.
    Only one may be set on a feed item.

    :param app: the ID of a :ref:`feed app <feed-apps>`.
    :type app: int|null
    :param collection: the ID of a :ref:`collection <rocketfuel>`.
    :type collection: int|null

    .. code-block:: json

        {
            "carrier": null,
            "category": null,
            "collection": 4,
            "region": 1
        }

    **Response**

    A representation of the newly-created :ref:`feed item <feed-items>`.

    :status 201: successfully created.
    :status 400: submission error, see the error message in the response body
        for more detail.
    :status 403: not authorized.


Update
======

.. http:patch:: /api/v2/feed/items/(int:id)/

    Update the properties of a feed item.

    **Request**

    :param carrier: the ID of a :ref:`carrier <carriers>`. If defined, it will
        restrict this feed item to only be viewed by users of this carrier.
    :type carrier: int|null
    :param category: the slug of a :ref:`category <categories>`. If defined,
        it will restrict this feed item to only be viewed by users browsing
        this category.
    :type category: slug|null
    :param region: the ID of a :ref:`region <regions>`. If defined, it will
        restrict this feed item to only be viewed in this region.
    :type region: int|null

    The following parameters define the object contained by this feed item.
    Only one may be set on a feed item.

    :param app: the ID of a :ref:`feed app <feed-apps>`.
    :type app: int|null
    :param collection: the ID of a :ref:`collection <rocketfuel>`.
    :type collection: int|null

    **Response**

    A serialization of the updated :ref:`feed item <feed-items>`.

    :status 200: successfully updated.
    :status 400: submission error, see the error message in the response body
        for more detail.
    :status 403: not authorized.


Delete
======

.. http:delete:: /api/v2/feed/items/(int:id)/

    Delete a feed item.

    **Request**

    :param id: the ID of the feed item.
    :type id: int

    **Response**

    :status 204: successfully deleted.
    :status 403: not authorized.


.. _feed-apps:

---------
Feed Apps
---------

A feed app is a thin wrapper around an :ref:`app <app>`, object containing
additional metadata related to its feature in the feed. A feed app represents
a featured app, a single app that is highlighted on its own in the feed.

Feed apps are represented thusly:

.. code-block:: json

    {
        "app": {
            "data": "..."
        },
        "background_color": "#A90000",
        "color": "ruby",
        "description": {
            "en-US": "A featured app",
            "fr": "Une application sélectionnée"
        },
        "type": "icon",
        "background_image": "http://somecdn.com/someimage.png"
        "id": 1
        "preview": null,
        "pullquote_attribute": null,
        "pullquote_rating": null,
        "pullquote_text": null,
        "slug": "app-of-the-month",
        "url": "/api/v2/feed/apps/1/"
    }

``app``
    *object* - the full representation of an :ref:`app <app>`.
``background_color``
    *string* - background color in 6-digit hex format prepended by a hash. Must
    be one of ``#CE001C``, ``#F78813``, ``#00953F``, ``#0099D0``, ``#1E1E9C``,
    ``#5A197E``, ``#A20D55``.
``color``
    *string* - color code name. The actual color values are defined in the
    frontend. Currently one of ``ruby``, ``amber``, ``emerald``, ``topaz``,
    ``sapphire``, ``amethyst``, ``garnet``.
``description``
    *string|null* - a :ref:`translated <overview-translations>` description of
    the app being featured.
``type``
    *string* - describes how the feed app will be displayed or featured. Can be
    ``icon``, ``image``, ``description``, ``quote``, ``preview``.
``id``
    *int* - the ID of this feed app.
``image``
    *string* - header graphic or background image
``preview``
    *object|null* - a featured :ref:`preview <screenshot-response-label>`
    (screenshot or video) of the app.
``pullquote_attribute``
    *object|null* - a :ref:`translated <overview-translations>` attribute of the
    pull quote.
``pullquote_rating``
    *integer|null* - a numeric rating of the pull quote between 1 and 5
    (inclusive).
``pullquote_text``
    *object|null* - the :ref:`translated <overview-translations>` text of a pull
    quote to feature with the app
``slug``
    *string* - a slug to use in URLs for the featured app
``url``
    *string|null* - the permanent URL for this feed app.


List
====

.. http:get:: /api/v2/feed/apps/

    A listing of feed apps.

    **Response**

    :param meta: :ref:`meta-response-label`.
    :type meta: object
    :param objects: A :ref:`listing <objects-response-label>` of
        :ref:`feed apps <feed-apps>`.
    :type objects: array


Detail
======

.. http:get:: /api/v2/feed/apps/(int:id)/

    Detail of a specific feed app.

    **Request**

    :param id: the ID of the feed app.
    :type id: int

    **Response**

    A representation of the :ref:`feed app <feed-apps>`.


Create
======

.. http:post:: /api/v2/feed/apps/

    Create a feed app.

    **Request**

    :param app: the ID of a :ref:`feed app <feed-apps>`.
    :type app: int|null
    :param background_color: [DEPRECATED] color in six-digit hex (with hash prefix)
    :type background_color: string
    :param color: primary color used to style. Actual hex value defined in
        frontend.
    :type color: string
    :param background_image_upload_url: a URL pointing to an image
    :type background_image_upload_url: string
    :param description: a :ref:`translated <overview-translations>` description
        of the app being featured.
    :type description: object|null
    :param type: can be ``icon``, ``image``, ``description``,
        ``quote``, or ``preview``.
    :type type: string
    :param preview: the ID of a :ref:`preview <screenshot-response-label>` to
        feature with the app.
    :type preview: int|null
    :param pullquote_attribute: a :ref:`translated <overview-translations>`
        attribution of the pull quote.
    :type pullquote_attribute: object|null
    :param pullquote_rating: a numeric rating of the pull quote between 1 and 5
        (inclusive).
    :type pullquote_rating: int|null
    :param pullquote_text: the :ref:`translated <overview-translations>` text of
        a pull quote to feature with the app. Required if
        ``pullquote_attribute`` or ``pullquote_rating`` are defined.
    :type pullquote_text: object|null
    :param slug: unique slug to use in URLs for the featured app
    :type slug: string

    .. code-block:: json

        {
            "app": 710,
            "background_color": "#A90000",
            "color": "ruby",
            "background_image_upload_url": "http://imgur.com/XXX.jpg",
            "description": {
                "en-US": "A featured app",
                "fr": "Une application sélectionnée"
            },
            "type": "icon",
            "pullquote_rating": 4,
            "pullquote_text": {
                "en-US": "This featured app is excellent.",
                "fr": "Pommes frites"
            },
            "slug": "app-of-the-month"
        }

    **Response**

    A representation of the newly-created :ref:`feed app <feed-apps>`.

    :status 201: successfully created.
    :status 400: submission error, see the error message in the response body
        for more detail.
    :status 403: not authorized.

Update
======

.. http:patch:: /api/v2/feed/apps/(int:id)/

    Update the properties of a feed app.

    **Request**

    :param app: the ID of a :ref:`feed app <feed-apps>`.
    :type app: int|null
    :param background_color: background color in 6-digit hex format prepended
        by a hash. Must be one of ``#CE001C``, ``#F78813``, ``#00953F``,
        ``#0099D0``, ``#1E1E9C``, ``#5A197E``, ``#A20D55``.
    :type background_color: string
    :param color: primary color used to style. Actual hex value defined in
        frontend. Currently one of ``ruby``, ``amber``, ``emerald``, ``topaz``,
        ``sapphire``, ``amethyst``, ``garnet``.
    :type color: string
    :param background_image_upload_url: a URL pointing to an image
    :type background_image_upload_url: string
    :param description: a :ref:`translated <overview-translations>` description
        of the app being featured.
    :type description: object|null
    :param type: can be ``icon``, ``image``, ``description``,
       ``quote``, or ``preview``.
    :type type: string
    :param preview: the ID of a :ref:`preview <screenshot-response-label>` to
        feature with the app.
    :type preview: int|null
    :param pullquote_attribute: a :ref:`translated <overview-translations>`
        attribution of the pull quote.
    :type pullquote_attribute: object|null
    :param pullquote_rating: a numeric rating of the pull quote between 1 and 5
        (inclusive).
    :type pullquote_rating: int|null
    :param pullquote_text: the :ref:`translated <overview-translations>` text of
        a pull quote to feature with the app. Required if
        ``pullquote_attribute`` or ``pullquote_rating`` are defined.
    :type pullquote_text: object|null
    :param slug: unique slug to use in URLs for the featured app
    :type slug: string

    **Response**

    A representation of the newly-created :ref:`feed app <feed-apps>`.

    :status 200: successfully updated.
    :status 400: submission error, see the error message in the response body
        for more detail.
    :status 403: not authorized.


Delete
======

.. http:delete:: /api/v2/feed/apps/(int:id)/

    Delete a feed app.

    **Request**

    :param id: the ID of the feed app.
    :type id: int

    **Response**

    :status 204: successfully deleted.
    :status 403: not authorized.


Feed App Image
==============

One-to-one background image or header graphic used to display with the
feed app.

.. http:get:: /api/v2/feed/apps/(int:id|string:slug)/image/

    Get the image for a feed app.

    .. note:: Authentication is optional.


.. http:put:: /api/v2/feed/apps/(int:id|string:slug)/image/

    Set the image for a feed app. Accepts a data URI as the request
    body containing the image, rather than a JSON object.

    .. note:: Authentication and one of the 'Collections:Curate' permission or
        curator-level access to the feed app are required.


.. http:delete:: /api/v2/feed/apps/(int:id|string:slug)/image/

    Delete the image for a feed app.

    .. note:: Authentication and one of the 'Collections:Curate' permission or
        curator-level access to the feed app are required.

.. _feed-brands:

-----------
Feed Brands
-----------

A feed brand is a collection-like object that allows editors to quickly create
content without involving localizers by choosing from one of a number of
predefined, prelocalized titles.

Feed brands are represented thusly:

.. code-block:: json

    {
        'apps': [
            {
                'id': 1
            },
            {
                'id': 2
            }
        ],
        'id': 1,
        'layout': 'grid',
        'slug': 'potato',
        'type': 'hidden-gem',
        'url': '/api/v2/feed/brands/1/'
    }

``apps``
    *array* - a list of serializations of the member :ref:`apps <app>`.
``id``
    *int* - the ID of this feed brand.
``layout``
    *string* - a string indicating the way apps should be laid out in the
    brand's detail page. One of ``'grid'`` or ``'list'``.
``slug``
    *string* - a slug to use in URLs for the feed brand
``type``
    *string* - a string indicating the title and icon that should be displayed
    with this feed brand. See a
    `full list of options <https://github.com/mozilla/zamboni/blob/master/mkt/feed/constants.py>`_.
``url``
    *string|null* - the permanent URL for this feed brand.


List
====

.. http:get:: /api/v2/feed/brands/

    A listing of feed brands.

    **Response**

    :param meta: :ref:`meta-response-label`.
    :type meta: object
    :param objects: A :ref:`listing <objects-response-label>` of
        :ref:`feed brands <feed-brands>`.
    :type objects: array


Detail
======

.. http:get:: /api/v2/feed/brands/(int:id)/

    Detail of a specific feed brand.

    **Request**

    :param id: the ID of the feed brand.
    :type id: int

    **Response**

    A representation of the :ref:`feed brand <feed-brands>`.


Create
======

.. http:post:: /api/v2/feed/brands/

    Create a feed brand.

    **Request**

    :param apps: an ordered array of app IDs.
    :type apps: array
    :param layout: string indicating the way apps should be laid out in the
        brand's detail page. One of ``'grid'`` or ``'list'``.
    :type layout: string
    :param slug: a slug to use in URLs for the feed brand.
    :type slug: string
    :param type: a string indicating the title and icon that should be displayed
        with this feed brand. See a
        `full list of options <https://github.com/mozilla/zamboni/blob/master/mkt/feed/constants.py>`_.
    :type type: string

    .. code-block:: json

        {
            "apps": [19, 1, 44],
            "layout": "grid",
            "slug": "facebook-hidden-gem",
            "type": "hidden-gem"
        }

    **Response**

    A representation of the newly-created :ref:`feed brand <feed-brands>`.

    :status 201: successfully created.
    :status 400: submission error, see the error message in the response body
        for more detail.
    :status 403: not authorized.


Update
======

.. http:patch:: /api/v2/feed/brands/(int:id)/

    Update the properties of a feed brand.

    **Request**

    :param apps: an ordered array of app IDs. If it is included in PATCH
        requests, it will delete from the collection all apps not included.
    :type apps: array
    :param layout: string indicating the way apps should be laid out in the
        brand's detail page. One of ``'grid'`` or ``'list'``.
    :type layout: string
    :param slug:  a slug to use in URLs for the feed brand.
    :type slug: string
    :param type: a string indicating the title and icon that should be displayed
        with this feed brand. See a
        `full list of options <https://github.com/mozilla/zamboni/blob/master/mkt/feed/constants.py>`_.
    :type type: string

    .. code-block:: json

        {
            "layout": "grid",
            "slug": "facebook-hidden-gem",
            "type": "hidden-gem"
        }

    **Response**

    A representation of the updated :ref:`feed brand <feed-brands>`.

    :status 200: successfully updated.
    :status 400: submission error, see the error message in the response body
        for more detail.
    :status 403: not authorized.


Delete
======

.. http:delete:: /api/v2/feed/brands/(int:id)/

    Delete a feed brand.

    **Request**

    :param id: the ID of the feed brand.
    :type id: int

    **Response**

    :status 204: successfully deleted.
    :status 403: not authorized.


.. _feed-collections:

----------------
Feed Collections
----------------

A feed collection is a complex assemblage of apps with a variety of display
options.

Apps in feed collections may be grouped. The group they belong to, if set, is
represented as a :ref:`translated <overview-translations>` group name, which is
assigned to the ``group`` property of each app's serialization. If ungrouped,
``group`` will be ``null``.

Feed collections are represented thusly:

.. code-block:: json

    {
        'apps': [
            {
                'id': 1,
                'group': {
                    'en-US': 'Games',
                    'fr': 'Jeux'
                },
                ...
            },
            {
                'id': 2,
                'group': {
                    'en-US': 'Games',
                    'fr': 'Jeux'
                },
                ...
            },
            {
                'id': 3,
                'group': {
                    'en-US': 'Tools',
                    'fr': 'Outils'
                },
                ...
            }
        ],
        'background_color': '#00AACC',
        'description': {
            'en-US': 'A description of my collection.'
        },
        'id': 19,
        'name': {
            'en-US': 'My awesome collection'
        },
        'slug': 'potato',
        'type': 'promo',
        'url': '/api/v2/feed/collections/1/'
    }

``apps``
    *array* - a list of serializations of the member :ref:`apps <app>`.
``background_color``
    *string* - background color in 6-digit hex format prepended by a hash. Must
    be one of ``#CE001C``, ``#F78813``, ``#00953F``, ``#0099D0``, ``#1E1E9C``,
    ``#5A197E``, ``#A20D55``.
``description``
    *object|null* a :ref:`translated <overview-translations>` description of
    the collection.
``id``
    *int* - the ID of this collection.
``name``
    *object* a :ref:`translated <overview-translations>` name of the
    collection.
``slug``
    *string* - a slug to use in URLs for the collection
``type``
    *string* - a string indicating the display type of the collection. Must be
    one of ``promo`` or ``listing``.
``url``
    *string|null* - the permanent URL for this collection.


.. _feed-collections-grouped:

When creating or updating a feed collection, the ``apps`` parameter may take
two forms:

1. An array of app IDs. This will result in the collection's apps being
   ungrouped.

.. code-block:: json

    {
        'apps': [1, 18, 3, 111, 98, 231]
    }

2. An array of objects, each with an ``apps`` property containing app IDs and
   a :ref:`translated <overview-translations>` ``name`` property defining the
   name of the group for those apps. This will result in the collection's apps
   being grouped as specified.

.. code-block:: json

    {
        'apps': [
            {
                'apps': [1, 18, 3],
                'name': {
                    'en-US': 'Games',
                    'fr': 'Jeux'
                }
            },
            {
                'apps': [111, 98, 231],
                'name': {
                    'en-US': 'Tools',
                    'fr': 'Outils'
                }
            }
        ]
    }


List
====

.. http:get:: /api/v2/feed/collections/

    A listing of feed collections.

    **Response**

    :param apps: an ordered array of :ref:`app serializations <app>`..
    :type apps: array
    :param meta: :ref:`meta-response-label`.
    :type meta: object
    :param objects: A :ref:`listing <objects-response-label>` of
        :ref:`feed collections <feed-collections>`.
    :type objects: array


Detail
======

.. http:get:: /api/v2/feed/collections/(int:id)/

    Detail of a specific feed collection.

    **Request**

    :param id: the ID of the feed collection.
    :type id: int

    **Response**

    A representation of the :ref:`feed collection <feed-collections>`.


Create
======

.. http:post:: /api/v2/feed/collections/

    Create a feed collection.

    **Request**

    :param apps: a grouped or ungrouped
        :ref:`app list <feed-collections-grouped>`.
    :param background_image_upload_url: a URL pointing to an image
    :type background_image_upload_url: string
    :param background_color: [DEPRECATED] a hex color used in display of the
        collection.  Currently must be one of ``#B90000``, ``#FF4E00``,
        ``#CD6723``, ``#00AACC``, ``#5F9B0A``, or ``#2C393B``.
    :type background_color: string
    :param color: primary color used to style. Actual hex value defined in
        frontend. Currently one of ``ruby``, ``amber``, ``emerald``, ``topaz``,
        ``sapphire``, ``amethyst``, ``garnet``.
    :type color: string
    :param description: a :ref:`translated <overview-translations>` description
        of the feed collection.
    :type description: object|null
    :param name: a :ref:`translated <overview-translations>` name of the
        collection.
    :type name: object
    :param slug: a slug to use in URLs for the collection.
    :type slug: string
    :param type: a string indicating the display type of the collection. Must
        be one of ``promo`` or ``listing``.
    :type type: string

    .. code-block:: json

        {
            "apps": [984, 19, 345, 981],
            "background_image_upload_url": "http://imgur.com/XXX.jpg",
            "color": "#B90000",
            "description": {
                "en-US": "A description of my collection."
            },
            "id": 19,
            "name": {
                "en-US": "My awesome collection"
            },
            "slug": "potato",
            "type": "promo"
        }

    **Response**

    A representation of the newly-created :ref:`feed collection
    <feed-collections>`.

    :status 201: successfully created.
    :status 400: submission error, see the error message in the response body
        for more detail.
    :status 403: not authorized.


Update
======

.. http:patch:: /api/v2/feed/collections/(int:id)/

    Update the properties of a collection.

    **Request**

    :param apps: a grouped or ungrouped
        :ref:`app list <feed-collections-grouped>`. If included in PATCH
        requests, it will delete from the collection all apps not included.
    :type apps: array
    :param background_image_upload_url: a URL pointing to an image
    :type background_image_upload_url: string
    :param background_color: [DEPRECATED] a hex color used in display of the
        collection.  Currently must be one of ``#B90000``, ``#FF4E00``,
        ``#CD6723``, ``#00AACC``, ``#5F9B0A``, or ``#2C393B``.
    :param color: primary color used to style. Actual hex value defined in
        frontend. Currently one of ``ruby``, ``amber``, ``emerald``, ``topaz``,
        ``sapphire``, ``amethyst``, ``garnet``.
    :type color: string
    :param description: a :ref:`translated <overview-translations>` description
        of the feed collection.
    :type description: object|null
    :param name: a :ref:`translated <overview-translations>` name of the
        collection.
    :type name: object
    :param slug: a slug to use in URLs for the collection.
    :type slug: string
    :param type: a string indicating the display type of the collection. Must
        be one of ``promo`` or ``listing``.
    :type type: string

    .. code-block:: json

        {
            "apps": [912, 42, 112],
            "color": "#B90000"
            "background_image_upload_url": "http://imgur.com/XXX.jpg",
            "description": {
                "en-US": "A description of my collection."
            },
            "name": {
                "en-US": "My awesome collection"
            },
            "slug": "potato",
            "type": "promo"
        }

    **Response**

    A representation of the updated :ref:`feed collection <feed-collections>`.

    :status 200: successfully updated.
    :status 400: submission error, see the error message in the response body
        for more detail.
    :status 403: not authorized.


Delete
======

.. http:delete:: /api/v2/feed/collections/(int:id)/

    Delete a feed collection.

    **Request**

    :param id: the ID of the feed collection.
    :type id: int

    **Response**

    :status 204: successfully deleted.
    :status 403: not authorized.


.. _feed-shelves:

--------------
Operator Shelf
--------------

An operator shelf is a collection-like object that provides a centralized place
for operators to showcase content to their customers. They are always bound to
category + region pairs, and are only shown to users browsing from the
specified category and region.

Operator shelves are represented thusly:

.. code-block:: json

    {
        "apps": [
            {
                "id": 1
            },
            {
                "id": 2
            }
        ],
        "background_image": "http://somecdn.com/someimage.png",
        "background_image_landing": "http://somecdn.com/some-other-image.png",
        "carrier": "telefonica",
        "description": {
            "en-US": "A description of my collection."
        },
        "id": 19,
        "is_published": false,
        "name": {
            "en-US": "My awesome collection"
        },
        "region": "br",
        "slug": "potato",
        "url": "/api/v2/feed/shelves/1/"
    }

``apps``
    *array* - a list of serializations of the member :ref:`apps <app>`.
``background_image``
    *string* - the URL to an image used while displaying the operator shelf.
``background_image_landing``
    *string* - the URL to an image used while displaying the operator
    shelf landing page.
``carrier``
    *string* - the slug of the :ref:`carrier <carriers>` the operator shelf
    belongs to.
``description``
    *string|null* - a :ref:`translated <overview-translations>` description of
    the operator shelf.
``id``
    *int* - the ID of this operator shelf.
``is_published``
    *boolean* - whether the shelf is published on a feed in its carrier/region.
``name``
    *string* - a :ref:`translated <overview-translations>` name for the
    operator shelf.
``region``
    *string* - the slug of the :ref:`region <regions>` the operator shelf
    belongs to.
``slug``
    *string* - a slug to use in URLs for the operator shelf
``url``
    *string|null* - the permanent URL for the operator shelf.


List
====

.. http:get:: /api/v2/feed/shelves/

    A listing of operator shelves.

    **Response**

    :param meta: :ref:`meta-response-label`.
    :type meta: object
    :param objects: A :ref:`listing <objects-response-label>` of
        :ref:`operator shelves <feed-shelves>`.
    :type objects: array


List User's
===========

.. http:get:: /api/v2/account/shelves/

    A listing of operator shelves upon which the authenticating user has
    permission to administer.

    **Response**

    A :ref:`listing <objects-response-label>` of :ref:`operator shelves
        <feed-shelves>`.


Detail
======

.. http:get:: /api/v2/feed/shelves/(int:id|string:slug)/

    Detail of a specific operator shelf.

    **Request**

    :param id: the ID of the operator shelf.
    :type id: int

    **Response**

    A representation of the :ref:`operator shelf <feed-shelves>`.


Create
======

.. http:post:: /api/v2/feed/shelves/

    Create an operator shelf.

    **Request**

    :param apps: an ordered array of app IDs.
    :type apps: array
    :param background_image_upload_url: a URL pointing to an image
    :type background_image_upload_url: string
    :param background_image_landing_upload_url: a URL pointing to an image
    :type background_image_landing_upload_url: string
    :param carrier: the slug of a :ref:`carrier <carriers>`.
    :type carrier: string
    :param description: a :ref:`translated <overview-translations>` description
        of the app being featured.
    :type description: object|null
    :param name: a :ref:`translated <overview-translations>` name of the
        collection.
    :type name: object
    :param region: the slug of a :ref:`region <regions>`.
    :type region: string
    :param slug: a slug to use in URLs for the operator shelf.
    :type slug: string

    .. code-block:: json

        {
            "apps": [19, 1, 44],
            "background_image_upload_url": "http://imgur.com/XXX.jpg",
            "background_image_landing_upload_url": "http://imgur.com/YYY.jpg",
            "carrier": "telefonica",
            "description": {
                "en-US": "A list of Telefonica's Favorite apps."
            },
            "name": {
                "en-US": "Telefonica's Favorite Apps"
            },
            "region": "br",
            "slug": "telefonica-brazil-shelf"
        }

    **Response**

    A representation of the newly-created :ref:`operator shelf <feed-shelves>`.

    :status 201: successfully created.
    :status 400: submission error, see the error message in the response body
        for more detail.
    :status 403: not authorized.


Update
======

.. http:patch:: /api/v2/feed/shelves/(int:id|string:slug)/

    Update the properties of an operator shelf.

    **Request**

    :param apps: an ordered array of app IDs.
    :type apps: array
    :param background_image_upload_url: a URL pointing to an image
    :type background_image_upload_url: string
    :param background_image_landing_upload_url: a URL pointing to an image
    :type background_image_landing_upload_url: string
    :param carrier: the slug of a :ref:`carrier <carriers>`.
    :type carrier: string
    :param description: a :ref:`translated <overview-translations>` description
        of the app being featured.
    :type description: object|null
    :param name: a :ref:`translated <overview-translations>` name of the
        collection.
    :type name: object
    :param region: the slug of a :ref:`region <regions>`.
    :type region: string
    :param slug: a slug to use in URLs for the operator shelf.
    :type slug: string

    .. code-block:: json

        {
            "apps": [19, 1, 44],
            "background_image_upload_url": "http://imgur.com/XXX.jpg",
            "background_image_landing_upload_url": "http://imgur.com/YYY.jpg",
            "carrier": "telefonica",
            "description": {
                "en-US": "A list of Telefonica's Favorite apps."
            },
            "name": {
                "en-US": "Telefonica's Favorite Apps"
            },
            "region": "br",
            "slug": "telefonica-brazil-shelf"
        }

    **Response**

    A representation of the updated :ref:`operator shelf <feed-shelves>`.

    :status 200: successfully updated.
    :status 400: submission error, see the error message in the response body
        for more detail.
    :status 403: not authorized.


Delete
======

.. http:delete:: /api/v2/feed/shelves/(int:id|string:slug)/

    Delete an operator shelf.

    **Request**

    :param id: the ID of the operator shelf.
    :type id: int

    **Response**

    :status 204: successfully deleted.
    :status 403: not authorized.


Image
=====

One-to-one background image or header graphic used to display with the operator
shelf.

.. http:get:: /api/v2/feed/shelves/(int:id|string:slug)/image/

    Get the image for an operator shelf.


.. http:put:: /api/v2/feed/shelves/(int:id|string:slug)/image/

    Set the image for an operator shelf. Accepts a data URI as the request
    body containing the image, rather than a JSON object.


.. http:delete:: /api/v2/feed/shelves/(int:id|string:slug)/image/

    Delete the image for an operator shelf.


-------
Builder
-------

.. http:put:: /api/v2/feed/builder/

    Sets feeds by region. For each region passed in, the builder
    will delete all of the carrier-less :ref:`feed items <feed-items>` for
    that region and then batch create feed items in the order that feed
    element IDs are passed in for that region.

    **Request**

    .. code-block:: json

        {
            'us': [
                ['collection', 52],
                ['app', 36],
                ['brand, 123],
                ['app', 66]
            ],
            'cn': [
                ['app', 36],
                ['collection', 52],
                ['brand', 2313]
                ['brand, 123],
            ],
            'hu': [],  // Passing in an empty array will empty that feed.
        }

    - The keys of the request are region slugs.
    - The region slugs point to two-element arrays.
    - The first element of the array is the item type. It can be
        ``app``, ``collection``, or ``brand``.
    - The second element of the array is the ID of a feed element.
    - It can be the ID of a :ref:`FeedApp  <feed-apps>`, or
        :ref:`FeedBrand <feed-brands>`.
    - Order matters.

    **Response**

    :status 201: success.
    :status 400: bad request.
    :status 403: not authorized.


.. _feed-search:

-------------------
Feed Element Search
-------------------

.. http:get:: /api/v2/feed/elements/search?q=(str:q)

    Search for feed elements given a search parameter.

    **Request**

    :param q: searches names and slugs
    :type q: str


    **Response**

    :param apps: :ref:`feed apps <feed-apps>`
    :type apps: array
    :param brands: :ref:`feed brands <feed-brands>`
    :type brands: array
    :param collections: :ref:`feed collections <feed-collections>`
    :type collections: array
    :param shelves: :ref:`feed shelves <feed-shelves>`
    :type shelves: array

    .. code-block:: json

        {
            "apps": [
                {
                    "id": 343,
                    ...
                },
            ],
            "brands": [
                {
                    "id": 143,
                    ...
                },
            ],
            "collections": [
                {
                    "id": 543,
                    ...
                },
            ],
            "shelves": [
                {
                    "id": 643,
                    ...
                },
            ],
        }
