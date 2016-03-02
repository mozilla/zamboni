.. _addons:
.. versionadded:: 2

==================
Firefox OS Add-ons
==================

The two main resources that are manipulated through this API are
:ref:`Add-ons <addon-detail>` and :ref:`Add-ons Versions <addon-version-detail>`.


Add-on
======

Detail
------

.. _addon-detail:

.. http:get:: /api/v2/extensions/extension/(int:id)|(string:slug)/

    .. note::
        Non public add-ons can only be viewed by their authors or extension
        reviewers (users with the *ContentTools:AddonReview* permission)

    A single add-on.

    **Example Response**:

    .. code-block:: json

        {
          "id": 1,
          "author": "Mozilla",
          "description": null,
          "disabled": false,
          "device_types": ["firefoxos"],
          "icons": {
            "64": "https://example.com/uploads/extensions_icons/0/1-64.png?m=1a1337",
            "128": "https://example.com/uploads/extensions_icons/0/1-128.png?m=1a1337",
          }
          "latest_version": {
            "id": 1,
            "download_url": "https://example.com/downloads/extension/ce6b52d231154a27a1c54b2648c10379/1/extension-0.1.zip",
            "unsigned_download_url": "https://example.com/downloads/extension/unsigned/ce6b52d231154a27a1c54b2648c10379/1/extension-0.1.zip",
            "status": "public",
            "version": "0.1"
          },
          "last_updated": "2015-09-04T16:16:39",
          "latest_public_version": {
            "id": 1,
            "download_url": "https://example.com/downloads/extension/ce6b52d231154a27a1c54b2648c10379/1/extension-0.1.zip",
            "unsigned_download_url": "https://example.com/downloads/extension/unsigned/ce6b52d231154a27a1c54b2648c10379/1/extension-0.1.zip",
            "status": "public",
            "version": "0.1"
          },
          "mini_manifest_url": "https://example.com/extension/ce6b52d231154a27a1c54b2648c10379/manifest.json",
          "name": {
            "en-US": "My Lîttle Extension"
          },
          "slug": "my-lîttle-extension",
          "status": "public",
          "uuid": "be98056d6963461eb543bea2ddf3b9af"
        }

    .. note::

        The ``name`` and ``description`` fields are user-translated fields and have a dynamic type
        depending on the query. See :ref:`translations <overview-translations>`.

    :resjson int id: The add-on id.
    :resjson string author: The add-on author, if specified in the manifest.
    :resjson string|object|null description: The add-on description.
    :resjson boolean disabled: Boolean indicating whether the developer has disabled
        their add-on or not.
    :resjson string device_types: The devices the add-on is compatible with.
    :resjson object icons: An object containing information about the app icons. The keys represent icon sizes, the values the corresponding URLs.
    :resjson string|null last_updated: The latest date a version was published at for this add-on.
    :resjson object latest_version: The latest :ref:`add-on version <addon-version-detail>` available for this extension.
    :resjson object latest_public_version: The latest *public* :ref:`add-on version <addon-version-detail>` available for this extension.
    :resjson string mini_manifest_url: The (absolute) URL to the `mini-manifest <https://developer.mozilla.org/docs/Mozilla/Marketplace/Options/Packaged_apps#Publishing_on_Firefox_Marketplace>`_ for that add-on. That URL may be a 404 if the add-on is not public yet.
    :resjson string|object name: The add-on name.
    :resjson string slug: The add-on slug (unique string identifier that can be used
        instead of the id to retrieve an add-on).
    :resjson string status: The add-on current status.
        Can be *incomplete*, *pending*, or *public*.
    :resjson string uuid: The add-on uuid, used internally for URLs and for blocklisting.

    :param int id: The add-on id
    :param string slug: The add-on slug

    :status 200: successfully completed.
    :status 403: not allowed to access this object.
    :status 404: not found.

List
----

.. http:get:: /api/v2/extensions/extension/

    .. note:: Requires authentication.

    A list of add-ons you have submitted.

    :resjson object meta: :ref:`meta-response-label`.
    :resjson array objects: An array of :ref:`add-ons <addon-detail>`.

    :status 200: successfully completed.
    :status 403: not authenticated.

Update
------

.. http:patch:: /api/v2/extensions/extension/(int:id)|(string:slug)/

    .. note:: Requires authentication and ownership of the Add-on.

    Update some properties of an add-on.

    :param int id: The add-on id
    :param string slug: The add-on slug.

    :reqjson boolean disabled: Boolean indicating whether the developer has disabled
        their add-on or not.
    :reqjson string slug: The add-on slug (unique string identifier that can be used
        instead of the id to retrieve an add-on).

    :status 200: successfully completed.
    :status 403: not allowed to access this object.
    :status 404: not found.

Search
------

.. _addon-search-label:

.. http:get:: /api/v2/extensions/search/

    Search through *public* add-ons.

    All query parameters are optional. The default sort order when the `sort`
    parameter is absent depends on whether a search query (`q`) is present or
    not:

        * If a search query is passed, order by relevance.
        * If no search query is passed, order by popularity descending.

    :param string q: The search query.
    :param string author: Filter by author. Requires a case-insensitive
        exact match of the author field.
    :param string sort: The field(s) to sort by. One or more of 'popularity',
        'created', 'name', 'reviewed'. In every case except 'name', sorting is
        done in descending order.

    :resjson object meta: :ref:`meta-response-label`.
    :resjson array objects: An array of :ref:`add-ons <addon-detail>`.

    :status 200: successfully completed.


Delete
------

.. _addon-delete:

.. http:delete:: /api/v2/extensions/extension/(int:id)|(string:slug)/

    .. note:: Requires authentication. Only works on your own Add-ons.

    Delete an add-on. This action is irreversible.


Blocking and Unblocking
-----------------------

.. _addon-block:

.. http:post:: /api/v2/extensions/extension/(int:id)|(string:slug)/block/

    .. note:: Requires authentication and admin rights (*Admin:%s* permission).

    Blocks an add-on.

    When in this state the Extension should not be editable by the developers
    at all; not visible publicly; not searchable by users; but should be shown
    in the developer's dashboard, as 'Blocked'.

.. _addon-unblock:

.. http:post:: /api/v2/extensions/extension/(int:id)|(string:slug)/unblock/

    .. note:: Requires authentication and admin rights (*Admin:%s* permission).

    Unblocks an add-on. It should restore its status according to the :ref:`rules
    below <addon_statuses>`.


Add-on Versions
===============


Detail
------

.. _addon-version-detail:

.. http:get:: /api/v2/extensions/extension/(int:id)|(string:slug)/versions/(int:version_id)/

    .. note::
        Non public add-ons versions can only be viewed by their authors or
        extension reviewers (users with the *ContentTools:AddonReview* permission)

    A single add-on version.

    **Example Response**:

    .. code-block:: json

        {
          "id": 1,
          "created": "2015-09-28T10:02:23",
          "download_url": "https://marketplace.firefox.com/downloads/extension/ce6b52d231154a27a1c54b2648c10379/42/extension-0.1.zip",
          "reviewer_mini_manifest_url": "https://marketplace.firefox.com/extension/reviewers/ce6b52d231154a27a1c54b2648c10379/42/manifest.json",
          "unsigned_download_url": "https://marketplace.firefox.com/downloads/extension/unsigned/ce6b52d231154a27a1c54b2648c10379/42/extension-0.1.zip",
          "status": "public",
          "version": "0.1"
        }

    :resjson string created: The creation date for this version.
    :resjson string download_url: The (absolute) URL to the latest signed package for that add-on. That URL may be a 404 if the add-on is not public.
    :resjson string reviewer_mini_manifest_url: The (absolute) URL to the reviewer-specific mini_manifest URL (allowing reviewers to install a non-public version) for this version. Only users with ContentTools:AddonReview permission may access it.
    :resjson string status: The add-on version current status. Can be *pending*, *obsolete*, *public* or *rejected*.
    :resjson string unsigned_download_url: The (absolute) URL to the latest *unsigned* package for that add-on. Only the add-on author or users with ContentTools:AddonReview permission may access it.
    :resjson string version: The version number for this add-on version.

    :param int id: The add-on id
    :param string slug: The add-on slug
    :param int version_id: The add-on version id

    :status 200: successfully completed.
    :status 403: not allowed to access this object.
    :status 404: not found.

List
----

.. http:get:: /api/v2/extensions/extension/(int:id)|(string:slug)/versions/

    .. note::
        Non public add-ons versions can only be viewed by their authors or
        extension reviewers (users with the *ContentTools:AddonReview* permission)

    A list of versions attached to an add-on.

    :resjson object meta: :ref:`meta-response-label`.
    :resjson array objects: An array of :ref:`add-ons versions <addon-version-detail>`.

    :status 200: successfully completed.
    :status 403: not allowed.
    :status 404: add-on not found.

Delete
------

.. _addon-version-delete:

.. http:delete:: /api/v2/extensions/extension/(int:id)|(string:slug)/versions/(int:version_id)/

    .. note::
        Requires authentication. Only works on versions attached to your
        your own add-ons.

    Delete an add-on version. This action is irreversible.

.. _addon_statuses:

Add-on Statuses
===============

* There are 5 possible values for the ``status`` property of an add-on: *public*, *pending*, *rejected*, *incomplete* or *blocked*.
* There are 4 possible values for the ``status`` property on an add-on version: *public*, *obsolete*, *pending*, *rejected*.

Add-on ``status`` directly depend on the ``status`` of its versions:

* Add-ons that are *blocked* never change.
* Add-ons with at least one *public* version are *public*.
* Add-ons with no *public* version and at least one *pending* version are *pending*.
* Add-ons with no *public* or *pending* version, and at least one *rejected* version are *rejected*.
* Add-ons with no *public*, *pending* or *rejected* version are *incomplete*.

Blocked Add-ons are hidden from the public. Reviewers and developers may still
access them, but can not make any modifications to them, only admins can.

In addition, Add-ons also have a ``disabled`` property that can be set to
``true`` by the developer to disable the add-on. Disabled add-ons are hidden
from the public and do not appear in the reviewers queue, but retain their
original status so they can be re-enabled by just switching ``disabled`` back
to ``false``.


Add-on and Add-on Version Submission
====================================

Submitting an Add-on or an Add-on Version is done in two steps. The client must
be logged in for all these steps and the user submitting the add-on or the
add-on version must have accepted the terms of use.

1. :ref:`Validate your package <addon_validation-post-label>`. The validation
   will return a validation id.
2. :ref:`Post your add-on <addon-post-label>` or
   :ref:`your add-on version <addon-version-post-label>` using the validation
   id obtained during the previous step. This will create an add-on or an
   add-on version and populate the data with the contents of the manifest.

.. _addon_validation:

Validation
----------

.. note:: The validation API does not require you to be authenticated, however
    you cannot create add-ons from those unauthenticated validations.
    To validate and then submit an add-on you must be authenticated with the
    same account for both steps.

.. _addon_validation-post-label:

.. http:post:: /api/v2/extensions/validation/

    Validate your add-on. The zip file containting your add-on should be sent
    as the POST body directly.
    A :ref:`validation result <addon_validation-response-label>` is returned.

    :reqheader Content-Type: *must* to be set to ``application/zip``
    :reqheader Content-Disposition: *must* be set to ``form-data; name="binary_data"; filename="extension.zip"``

    :status 201: successfully created, processed.
    :status 202: successfully created, still processing.
    :status 400: some errors were found in your add-on.

.. _addon_validation-response-label:

.. http:get:: /api/v2/extensions/validation/(string:id)/

    **Response**

    A single validation result. You should poll this API until it returns
    a result with the ``processed`` property set to ``true`` before moving on
    with the submission process.

    :resjson string id: the id of the validation.
    :resjson boolean processed: if the validation has been processed.
    :resjson boolean valid: if the validation passed.
    :resjson string validation: the resulting validation messages if it failed.
    :type validation: string

    :status 200: successfully completed.
    :status 404: validation not found.

.. _addon_creation:

Add-on Creation
---------------

.. _addon-post-label:

.. http:post:: /api/v2/extensions/extension/

    .. note:: Requires authentication and a successful validation result.

    Create an add-on. Note that an add-on version is created automatically for
    you.
    An :ref:`add-on <addon-detail>` is returned. Icons are processed
    asynchronously; as a result, the json data returned might not contain the
    final URL for the icons at this time.

    :reqjson string validation_id: the id of the
        :ref:`validation result <addon_validation>` for your add-on.
    :reqjson string message (optional): Notes for reviewers about the
                                        submission.

    :status 201: successfully created.
    :status 400: some errors were found in your add-on.

Add-on Version Creation
-----------------------

.. _addon-version-post-label:


.. http:post:: /api/v2/extensions/extension/(int:id)|(string:slug)/versions/

    .. note::
        Requires authentication, ownership of the add-on (which must not be in
        ``disabled`` state) and a successful validation result.

    Create an add-on version.

    :reqjson string validation_id: the id of the
        :ref:`validation result <addon_validation>` for your add-on version.
    :reqjson string message (optional): Notes for reviewers about the
                                        submission.

    :param int id: The add-on id
    :param string slug: The add-on slug

    :status 201: successfully created.
    :status 400: some errors were found in your add-on.
    :status 403: not allowed.
    :status 404: add-on not found.



Add-ons Review Queue
====================

Any add-on that is not disabled by its developer, and has at least one
*pending* version is shown in the review queue, even if the add-on itself is
currently public.

Add-ons are not directly published or rejected, Add-ons Versions are. Usually
the add-on ``latest_version`` is the version that needs to be reviewed.

Once a version is published, rejected or deleted, the parent Add-on ``status``
:ref:`can change as described above<addon_statuses>`.

List
----

.. http:get:: /api/v2/extensions/queue/

    .. note:: Requires authentication and the ContentTools:AddonReview permission.

    The list of add-ons in the review queue.

    :resjson object meta: :ref:`meta-response-label`.
    :resjson array objects: An array of :ref:`add-ons <addon-detail>`.

    :status 200: successfully completed.
    :status 403: not allowed.

Publishing
----------

.. http:post:: /api/v2/extensions/extension/(int:id)|(string:slug)/versions/(int:id)/publish/

    Publish an add-on version. Its file will be signed, its status updated to
    *public*.

    :param int id: The add-on id
    :param string slug: The add-on slug
    :param int version_id: The add-on version id
    :param string message (optional): Reviewer notes about publishing

    :status 202: successfully published.
    :status 403: not allowed to access this object or disabled add-on.
    :status 404: add-on not found in the review queue.

Rejecting
---------

.. http:post:: /api/v2/extensions/extension/(int:id)|(string:slug)/versions/(int:id)/reject/

    Reject an add-on version. Its status will be updated to *rejected*. The
    developer will have to submit it a new version with the issues fixed.

    :param int id: The add-on id
    :param string slug: The add-on slug
    :param int version_id: The add-on version id
    :param string message (optional): Reviewer notes about rejecting

    :status 202: successfully published.
    :status 403: not allowed to access this object or disabled add-on.
    :status 404: add-on not found in the review queue.

