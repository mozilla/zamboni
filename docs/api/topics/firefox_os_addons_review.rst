.. _addons_review:

=========================
Firefox OS Add-ons Review
=========================

.. warning::

    Firefox OS Add-ons in Marketplace are experimental and not yet available in
    production. This API is not ready for public consumption yet and can change
    at any moment.

Add-ons Queue
=============

.. http:get:: /api/v2/extensions/queue/

    .. note:: Requires authentication and the Extensions:Review permission.

    Returns the list of add-ons in the review queue. Any add-on with at least
    one pending version is shown in the queue, even if the add-on itself is
    currently public.

    **Request**

    The standard :ref:`list-query-params-label`.

    **Response**

    :param meta: :ref:`meta-response-label`.
    :type meta: object
    :param objects: A :ref:`listing <objects-response-label>` of :ref:`add-ons <addon-response-label>`.
    :type objects: array

    :status 200: successfully completed.
    :status 403: not authenticated.

Publishing Or Rejecting Add-ons
===============================

Add-on are not directly published or rejected, versions are. Usually the
add-on ``latest_version`` is the version that needs to be reviewed.

.. http:post:: /api/v2/extensions/extension/(int:id)|(string:slug)/versions/(int:id)/publish/

    Publish an add-on version. Its file will be signed, its status updated to
    "public". The corresponding add-on will inherit that status and will
    become available through :ref:`add-ons search <addon-search-label>`.

    **Response**

    :status 202: successfully published.
    :status 403: not allowed to access this object.
    :status 404: add-on not found in the review queue.

.. http:post:: /api/v2/extensions/extension/(int:id)|(string:slug)/versions/(int:id)/reject/

    Reject an add-on version. Its status will be updated to "rejected". The developer
    will have to submit it a new version with the issues fixed. 

    If the add-on has one ore more other versions that are public versions, it
    will stay "public". If it had no other public versions but had one or more
    pending versions, it will stay "pending". Otherwise, it will become "incomplete".

    **Request**

    :param comment: a comment from the reviewer
    :type comment: string

    **Response**

    :status 202: successfully published.
    :status 403: not allowed to access this object.
    :status 404: add-on not found in the review queue.
