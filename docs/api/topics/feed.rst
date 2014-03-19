.. _feed:
.. versionadded:: 2

====
Feed
====

The Marketplace Feed is a stream of content relevant to the user displayed on
the Marketplace home page. The feed is comprised of a number of :ref:`feed items
<feed-items>`, each containing a singular of piece of content. Currently, the
feed may include:

- :ref:`Apps <feed-apps>`
- :ref:`Collections <feed-collections>`

.. note::

    ``GET``, ``HEAD``, and ``OPTIONS`` requests to these endpoints may be made
    anonymously. Authentication and the ``Feed:Curate`` permission are required
    to make any other request.


.. _feed-items:

----------
Feed Items
----------

Feed items are represented thusly:

.. code-block:: json

    {
        "app": null,
        "carrier": "telefonica",
        "category": null,
        "collection": {
            "data": "..."
        }
        "id": 47,
        "item_type": "collection",
        "region": "br",
        "resource_url": "/api/v2/feed/items/47/"
    }

``app``
    *object|null* - the full representation of a :ref:`feed app <feed-apps>`.
``carrier``
    *string|null* - the slug of a :ref:`carrier <carriers>`. If
    defined, this feed item will only be available by users of that carrier.
``category``
    *int|null* - the ID of a :ref:`category <categories>`. If defined, this feed
    item will only be available to users browsing that category.
``collection``
    *object|null* - the full representation of a  :ref:`collection
    <collections>`.
``id``
    *int* the ID of this feed item.
``item_type``
    *string* - the type of object being represented by this feed item. This will
    always be usable as a key on the feed item instance to fetch that object's
    data (i.e. ``feeditem[feeditem['item_type']]`` will always be non-null).
``resource_url``
    *string* - the permanent URL for this feed item. 
``region``
    *string|null* - the slug of a :ref:`region <regions>`. If defined, this feed
    item will only be available in that region.


List
====

.. http:get:: /api/v2/feed/items/

    A listing of feed items.

    **Response**

    :param meta: :ref:`meta-response-label`.
    :type meta: object
    :param objects: A :ref:`listing <objects-response-label>` of
        :ref:`feed items <feed-items>`.
    :type objects: array


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
    :param category: the ID of a :ref:`category <categories>`. If defined, it
        will restrict this feed item to only be viewed by users browsing this
        category.
    :type category: int|null
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
    :param category: the ID of a :ref:`category <categories>`. If defined, it
        will restrict this feed item to only be viewed by users browsing this
        category.
    :type category: int|null
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
additional metadata related to its feature in the feed.

Feed apps are represented thusly:

.. code-block:: json

    {
        "app": {
            "data": "..."
        },
        "description": {
            "en-US": "A featured app",
            "fr": "Une application sélectionnée"
        },
        "id": 1
        "preview": null,
        "pullquote_attribute": null,
        "pullquote_rating": null,
        "pullquote_text": null,
        "url": "/api/v2/feed/apps/1/"
    }

``app``
    *object* - the full representation of an :ref:`app <app>`.
``description``
    *string|null* - a :ref:`translated <overview-translations>` description of
    the app being featured.
``id``
    *int* - the ID of this feed app.
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
    :param description: a :ref:`translated <overview-translations>` description
        of the app being featured.
    :type description: object|null
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

    .. code-block:: json

        {
            "app": 710,
            "description": {
                "en-US": "A featured app",
                "fr": "Une application sélectionnée"
            },
            "pullquote_rating": 4,
            "pullquote_text": {
                "en-US": "This featured app is excellent.",
                "fr": "Pommes frites"
            }
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
    :param description: a :ref:`translated <overview-translations>` description
        of the app being featured.
    :type description: object|null
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


.. _feed-collections:

-----------
Collections
-----------

A collection is a group of applications

.. note::

    The `name` and `description` fields are user-translated fields and have
    a dynamic type depending on the query.
    See :ref:`translations <overview-translations>`.


Listing
=======

.. http:get:: /api/v2/feed/collections/

    A listing of all collections.

    .. note:: Authentication is optional.

    **Request**:

    The following query string parameters can be used to filter the results:

    :param cat: a category ID/slug.
    :type cat: int|string
    :param region: a region ID/slug.
    :type region: int|string
    :param carrier: a carrier ID/slug.
    :type carrier: int|string

    Filtering on null values is done by omiting the value for the corresponding
    parameter in the query string.

.. _rocketfuel-fallback:

    If no results are found with the filters specified, the API will
    automatically use a fallback mechanism and try to change the values to null
    in order to try to find some results.

    The order in which the filters are set to null is:
        1. `region`
        2. `carrier`
        3. `region` and `carrier`.

    In addition, if that fallback mechanism is used, HTTP responses will have an
    additional `API-Fallback` header, containing the fields which were set to
    null to find the returned results, separated by a comma if needed, like this:

    `API-Fallback: region, carrier`

Create
======

.. http:post:: /api/v2/feed/collections/

    Create a collection.

    .. note:: Authentication and the 'Collections:Curate' permission are
        required.

    **Request**:

    :param author: the author of the collection.
    :type author: string
    :param background_color: the background of the overlay on the image when
        collection is displayed (hex-formatted, e.g. "#FF00FF"). Only applies to
        curated collections (i.e. when collection_type is 0).
    :type background_color: string|null
    :param can_be_hero: whether the collection may be featured with a hero
        graphic. This may only be set to ``true`` for operator shelves. Defaults
        to ``false``.
    :type can_be_hero: boolean
    :param carrier: the ID of the carrier to attach this collection to. Defaults
        to ``null``.
    :type carrier: int|null
    :param category: the ID of the category to attach this collection to.
        Defaults to ``null``.
    :type category: int|null
    :param collection_type: the type of collection to create.
    :type collection_type: int
    :param description: a description of the collection.
    :type description: string|object
    :param is_public: an indication of whether the collection should be
        displayed in consumer-facing pages. Defaults to ``false``.
    :type is_public: boolean
    :param name: the name of the collection.
    :type name: string|object
    :param region: the ID of the region to attach this collection to. Defaults
        to ``null``.
    :type region: int|null
    :param slug: a slug to use in URLs for the collection. Automatically
        generated if not specified.
    :type slug: string|null
    :param text_color: the color of the text displayed on the overlay on the
        image when collection is displayed (hex-formatted, e.g. "#FF00FF"). Only
        applies to curated collections (i.e. when collection_type is 0).
    :type text_color: string|null


Detail
======

.. http:get:: /api/v2/feed/collections/(int:id|string:slug)/

    Get a single collection.

    .. note:: Authentication is optional.


Update
======

.. http:patch:: /api/v2/feed/collections/(int:id|string:slug)/

    Update a collection.

    .. note:: Authentication and one of the 'Collections:Curate' permission or
        curator-level access to the collection are required.

    .. note:: The ``can_be_hero`` field may not be modified unless you have the
        ``Collections:Curate`` permission, even if you have curator-level
        access to the collection.

    **Request**:

    :param author: the author of the collection.
    :type author: string
    :param can_be_hero: whether the collection may be featured with a hero
        graphic. This may only be set to ``true`` for operator shelves. Defaults
        to ``false``.
    :type can_be_hero: boolean
    :param carrier: the ID of the carrier to attach this collection to.
    :type carrier: int|null
    :param category: the ID of the category to attach this collection to.
    :type category: int|null
    :param collection_type: the type of the collection.
    :type collection_type: int
    :param description: a description of the collection.
    :type description: string|object
    :param name: the name of the collection.
    :type name: string|object
    :param region: the ID of the region to attach this collection to.
    :type region: int|null
    :param slug: a slug to use in URLs for the collection.
    :type slug: string|null


    **Response**:

    A representation of the updated collection will be returned in the response
    body.

    :status 200: collection successfully updated.
    :status 400: invalid request; more details provided in the response body.


Duplicate
=========

.. http:post:: /api/v2/feed/collections/(int:id)/duplicate/

    Duplicate a collection, creating and returning a new one with the same
    properties and the same apps.

    .. note:: Authentication and one of the 'Collections:Curate' permission or
        curator-level access to the collection are required.

    .. note:: The ``can_be_hero`` field may not be modified unless you have the
        ``Collections:Curate`` permission, even if you have curator-level
        access to the collection.

    **Request**:

    Any parameter passed will override the corresponding property from the
    duplicated object.

    :param author: the author of the collection.
    :type author: string
    :param can_be_hero: whether the collection may be featured with a hero
        graphic. This may only be set to ``true`` for operator shelves. Defaults
        to ``false``.
    :type can_be_hero: boolean
    :param carrier: the ID of the carrier to attach this collection to.
    :type carrier: int|null
    :param category: the ID of the category to attach this collection to.
    :type category: int|null
    :param collection_type: the type of the collection.
    :type collection_type: int
    :param description: a description of the collection.
    :type description: string|object
    :param name: the name of the collection.
    :type name: string|object
    :param region: the ID of the region to attach this collection to.
    :type region: int|null
    :param slug: a slug to use in URLs for the collection.
    :type slug: string|null

    **Response**:

    A representation of the duplicate collection will be returned in the
    response body.

    :status 201: collection successfully duplicated.
    :status 400: invalid request; more details provided in the response body.


Delete
======

.. http:delete:: /api/v2/feed/collections/(int:id|string:slug)/

    Delete a single collection.

    .. note:: Authentication and the 'Collections:Curate' permission are
        required.

    **Response**:

    :status 204: collection successfully deleted.
    :status 400: invalid request; more details provided in the response body.
    :status 403: not authenticated or authenticated without permission; more
        details provided in the response body.


Add Apps
========

.. http:post:: /api/v2/feed/collections/(int:id|string:slug)/add_app/

    Add an application to a single collection.

    .. note:: Authentication and one of the 'Collections:Curate' permission or
        curator-level access to the collection are required.

    **Request**:

    :param app: the ID of the application to add to this collection.
    :type app: int

    **Response**:

    A representation of the updated collection will be returned in the response
    body.

    :status 200: app successfully added to collection.
    :status 400: invalid request; more details provided in the response body.


Remove Apps
===========

.. http:post:: /api/v2/feed/collections/(int:id|string:slug)/remove_app/

    Remove an application from a single collection.

    .. note:: Authentication and one of the 'Collections:Curate' permission or
        curator-level access to the collection are required.

    **Request**:

    :param app: the ID of the application to remove from this collection.
    :type app: int

    **Response**:

    A representation of the updated collection will be returned in the response
    body.

    :status 200: app successfully removed from collection.
    :status 205: app not a member of the collection.
    :status 400: invalid request; more details provided in the response body.


Reorder Apps
============

.. http:post:: /api/v2/feed/collections/(int:id|string:slug)/reorder/

    Reorder applications in a collection.

    .. note:: Authentication and one of the 'Collections:Curate' permission or
        curator-level access to the collection are required.

    **Request**:

    The body of the request must contain a list of apps in their desired order.

    Example:

    .. code-block:: json

        [18, 24, 9]

    **Response**:

    A representation of the updated collection will be returned in the response
    body.

    :status 200: collection successfully reordered.
    :status 400: all apps in the collection not represented in response body.
        For convenience, a list of all apps in the collection will be included
        in the response.

Image
=====

.. http:get:: /api/v2/feed/collections/(int:id|string:slug)/image/

    Get the image for a collection.

    .. note:: Authentication is optional.


.. http:put:: /api/v2/feed/collections/(int:id|string:slug)/image/

    Set the image for a collection. Accepts a data URI as the request
    body containing the image, rather than a JSON object.

    .. note:: Authentication and one of the 'Collections:Curate' permission or
        curator-level access to the collection are required.


.. http:delete:: /api/v2/feed/collections/(int:id|string:slug)/image/

    Delete the image for a collection.

    .. note:: Authentication and one of the 'Collections:Curate' permission or
        curator-level access to the collection are required.


Curators
========

Users can be given object-level access to collections if they are marked as
`curators`. The following API endpoints allow manipulation of a collection's
curators:

Listing
-------

.. http:get:: /api/v2/feed/collections/(int:id|string:slug)/curators/

    Get a list of curators for a collection.

    .. note:: Authentication and one of the 'Collections:Curate' permission or
        curator-level access to the collection are required.

    **Response**:

    Example:

    .. code-block:: json

        [
            {
                'display_name': 'Basta',
                'email': 'support@bastacorp.biz',
                'id': 30
            },
            {
                'display_name': 'Cvan',
                'email': 'chris@vans.com',
                'id': 31
            }
        ]


Add Curator
-----------

.. http:post:: /api/v2/feed/collections/(int:id|string:slug)/add_curator/

    Add a curator to this collection.

    .. note:: Authentication and one of the 'Collections:Curate' permission or
        curator-level access to the collection are required.

    **Request**:

    :param user: the ID or email of the user to add as a curator of this
        collection.
    :type user: int|string

    **Response**:

    A representation of the updated list of curators for this collection will be
    returned in the response body.

    :status 200: user successfully added as a curator of this collection.
    :status 400: invalid request; more details provided in the response body.
    :status 403: not authenticated or authenticated without permission; more
        details provided in the response body.


Remove Curator
--------------

.. http:post:: /api/v2/feed/collections/(int:id|string:slug)/remove_curator/

    Remove a curator from this collection.

    .. note:: Authentication and one of the 'Collections:Curate' permission or
        curator-level access to the collection are required.

    **Request**:

    :param user: the ID or email of the user to remove as a curator of this
        collection.
    :type user: int|string

    **Response**:

    :status 205: user successfully removed as a curator of this collection.
    :status 400: invalid request; more details provided in the response body.
    :status 403: not authenticated or authenticated without permission; more
        details provided in the response body.
