.. _addons:

==================
Firefox OS Add-ons
==================

.. warning::

    Firefox OS Add-ons in Marketplace are experimental and not yet available in
    production. This API is not ready for public consumption yet and can change
    at any moment.

Add-on Submission
=================

See the dedicated :ref:`Firefox OS Add-on Submission <addon_submission>` topic.

Add-on
======

.. note::

    The `name`, field is a user-translated fields and has a dynamic type
    depending on the query. See :ref:`translations <overview-translations>`.


.. http:get:: /api/v2/extensions/extension/

    .. note:: Requires authentication.

    Returns a list of add-ons you have submitted.

    **Request**

    The standard :ref:`list-query-params-label`.

    **Response**

    :param meta: :ref:`meta-response-label`.
    :type meta: object
    :param objects: A :ref:`listing <objects-response-label>` of :ref:`add-ons <addon-response-label>`.
    :type objects: array

    :status 200: successfully completed.
    :status 403: not authenticated.

.. _addon-response-label:

.. http:get:: /api/v2/extensions/extension/(int:id)|(string:slug)/

    .. note:: Non public add-ons can only be viewed by their authors.

    Returns a single add-on.

    **Response**

    :param download_url: The (absolute) URL to the latest signed package for that add-on.
    :type download_url: string
    :param name: The add-on name.
    :type name: string|object
    :param manifest_url: The (absolute) URL to the mini-manifest for that add-on.
    :type manifest_url: string
    :param slug: The add-on slug (unique string identifier that can be used
        instead of the id to retrieve an add-on).
    :type slug: string
    :param status: The add-on current status.
        Can be "incomplete", "pending", "public" or "rejected".
    :type status: string
    :param version: The add-on current version number.
    :type version: string

    :status 200: successfully completed.
    :status 403: not allowed to access this object.
    :status 404: not found.

Add-on Search
=============

.. _addon-search-label:

.. http:get:: /api/v2/extensions/search/

    .. note:: Only returns public add-ons. Search query is ignored for now.

    **Request**

    The standard :ref:`list-query-params-label`.

    **Response**

    :param meta: :ref:`meta-response-label`.
    :type meta: object
    :param objects: A :ref:`listing <objects-response-label>` of :ref:`add-ons <addon-response-label>`.
    :type objects: array

    :status 200: successfully completed.


Add-on Review
=============

See the dedicated :ref:`Firefox OS Add-on Review <addons_review>` topic.
