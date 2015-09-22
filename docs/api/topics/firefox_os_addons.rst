.. _addons:
.. versionadded:: 2

==================
Firefox OS Add-ons
==================

.. warning::

    Firefox OS Add-ons in Marketplace are experimental and not yet available in
    production. This API is not ready for public consumption yet and can change
    at any moment.

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
        reviewers (users with the *Extensions:Review* permission)

    A single add-on.

    **Example Response**:

    .. code-block:: json

        {
          "id": 1,
          "description": null,
          "latest_version": {
            "id": 1,
            "download_url": "https://example.com/downloads/extension/ce6b52d231154a27a1c54b2648c10379/1/extension-0.1.zip",
            "unsigned_download_url": "https://example.com/downloads/extension/unsigned/ce6b52d231154a27a1c54b2648c10379/1/extension-0.1.zip",
            "status": "public",
            "version": "0.1"
          },
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
          "status": "public"
        }

    .. note::

        The ``name`` and ``description`` fields are user-translated fields and have a dynamic type
        depending on the query. See :ref:`translations <overview-translations>`.

    :resjson int id: The add-on id.
    :resjson string|object|null description: The add-on description.
    :resjson object latest_version: The latest :ref:`add-on version <addon-version-detail>` available for this extension.
    :resjson object latest_public_version: The latest *public* :ref:`add-on version <addon-version-detail>` available for this extension.
    :resjson string mini_manifest_url: The (absolute) URL to the `mini-manifest <https://developer.mozilla.org/docs/Mozilla/Marketplace/Options/Packaged_apps#Publishing_on_Firefox_Marketplace>`_ for that add-on. That URL may be a 404 if the add-on is not public yet.
    :resjson string|object name: The add-on name.
    :resjson string slug: The add-on slug (unique string identifier that can be used
        instead of the id to retrieve an add-on).
    :resjson string status: The add-on current status.
        Can be *incomplete*, *pending*, or *public*.

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


Search
------

.. _addon-search-label:

.. http:get:: /api/v2/extensions/search/

    .. note:: Search query is ignored for now.

    A list of *public* add-ons.

    :resjson object meta: :ref:`meta-response-label`.
    :resjson array objects: An array of :ref:`add-ons <addon-detail>`.

    :status 200: successfully completed.


Delete
------

.. _addon-delete:

.. http:delete:: /api/v2/extensions/extension/(int:id)|(string:slug)/

    .. note:: Requires authentication. Only works on your own Add-ons.

    Delete an add-on. This action is irreversible.


Add-on Versions
===============


Detail
------

.. _addon-version-detail:

.. http:get:: /api/v2/extensions/extension/(int:id)|(string:slug)/versions/(int:version_id)/

    .. note::
        Non public add-ons versions can only be viewed by their authors or
        extension reviewers (users with the *Extensions:Review* permission)

    A single add-on version.

    **Example Response**:

    .. code-block:: json

        {
          "id": 1,
          "download_url": "https://marketplace.firefox.com/downloads/extension/ce6b52d231154a27a1c54b2648c10379/1/extension-0.1.zip",
          "unsigned_download_url": "https://marketplace.firefox.com/downloads/extension/unsigned/ce6b52d231154a27a1c54b2648c10379/1/extension-0.1.zip",
          "status": "public",
          "version": "0.1"
        }

    :resjson string download_url: The (absolute) URL to the latest signed package for that add-on. That URL may be a 404 if the add-on is not public.
    :resjson string status: The add-on version current status. Can be *pending*, *obsolete*, *public* or *rejected*.
    :resjson string unsigned_download_url: The (absolute) URL to the latest *unsigned* package for that add-on. Only the add-on author or users with Extensions:Review permission may access it.
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
        extension reviewers (users with the *Extensions:Review* permission)

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

* There are 3 possible values for the ``status`` property of an add-on: *public*, *pending* or *incomplete*.
* There are 4 possible values for the ``status`` property on an add-on version: *public*, *obsolete*, *pending*, *rejected*.

Add-on ``status`` directly depend on the ``status`` of its versions:

* Add-ons with at least one *public* version are *public*.
* Add-ons with no *public* version and at least one *pending* version are *pending*.
* Add-ons with no *public* or *pending* version are *incomplete*.


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
    An :ref:`add-on <addon-detail>` is returned.

    :reqjson string validation_id: the id of the
        :ref:`validation result <addon_validation>` for your add-on.

    :status 201: successfully created.
    :status 400: some errors were found in your add-on.

Add-on Version Creation
-----------------------

.. _addon-version-post-label:


.. http:post:: /api/v2/extensions/extension/(int:id)|(string:slug)/versions/

    .. note::
        Requires authentication, ownership of the add-on and a successful
        validation result.

    Create an add-on version.

    :reqjson string validation_id: the id of the
        :ref:`validation result <addon_validation>` for your add-on version.

    :param int id: The add-on id
    :param string slug: The add-on slug

    :status 201: successfully created.


Add-ons Review Queue
====================

Any add-on with at least one *pending* version is shown in the review queue,
even if the add-on itself is currently public.

Add-ons are not directly published or rejected, Add-ons Versions are. Usually
the add-on ``latest_version`` is the version that needs to be reviewed.

Once a version is published, rejected or deleted, the parent Add-on ``status``
:ref:`can change as described above<addon_statuses>`.

List
----

.. http:get:: /api/v2/extensions/queue/

    .. note:: Requires authentication and the Extensions:Review permission.

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

    :status 202: successfully published.
    :status 403: not allowed to access this object.
    :status 404: add-on not found in the review queue.

Rejecting
---------

.. http:post:: /api/v2/extensions/extension/(int:id)|(string:slug)/versions/(int:id)/reject/

    Reject an add-on version. Its status will be updated to *rejected*. The
    developer will have to submit it a new version with the issues fixed.

    :param int id: The add-on id
    :param string slug: The add-on slug
    :param int version_id: The add-on version id

    :status 202: successfully published.
    :status 403: not allowed to access this object.
    :status 404: add-on not found in the review queue.

