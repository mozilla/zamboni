.. _addons:

==================
Firefox OS Add-ons
==================

.. warning::

    Firefox OS Add-ons in Marketplace are experimental and not yet available in
    production. This API is not ready for public consumption yet and can change
    at any moment.

Addon Submission
================

See the dedicated :ref:`Firefox OS Addon Submission <addon_submission>` topic.

Addon
=====

.. note::

    The `name`, field is a user-translated fields and has a dynamic type
    depending on the query. See :ref:`translations <overview-translations>`.


.. http:get:: /api/v2/extension/extension/

    .. note:: Requires authentication.

    Returns a list of addons you have submitted.

    **Request**

    The standard :ref:`list-query-params-label`.

    **Response**

    :param meta: :ref:`meta-response-label`.
    :type meta: object
    :param objects: A :ref:`listing <objects-response-label>` of :ref:`addons <addon-response-label>`.
    :type objects: array

.. _addon-response-label:

.. http:get:: /api/v2/extensions/extension/(int:id)|(string:slug)/

    .. note:: Does not require authentication if your addon is public.

    **Response**

    :param name: The addon name.
    :type name: string|object
    :param slug: The addon slug (unique string identifier that can be used
        instead of the id to retrieve an addon).
    :type slug: string
    :param version: The addon current version number.
    :type version: string
    :param status: The addon current status.
        Can be "incomplete", "pending" or "public".
    :type status: string
    

    :status 200: successfully completed.
    :status 403: not allowed to access this object.
    :status 404: not found.