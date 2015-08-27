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

    Returns the list of add-ons in the review queue.

    **Request**

    The standard :ref:`list-query-params-label`.

    **Response**

    :param meta: :ref:`meta-response-label`.
    :type meta: object
    :param objects: A :ref:`listing <objects-response-label>` of :ref:`add-ons <addon-response-label>`.
    :type objects: array

    :status 200: successfully completed.
    :status 403: not authenticated.


.. http:get:: /api/v2/extensions/extension/(int:id)|(string:slug)/

    Returns a particular add-on from the review queue.

    **Response**

    An :ref:`add-on <addon-response-label>`.

    :status 200: successfully completed.
    :status 403: not allowed to access this object.
    :status 404: add-on not found in the review queue.


Publishing Or Rejecting Add-ons
===============================

.. http:post:: /api/v2/extensions/queue/(int:id)|(string:slug)/publish/

    Publish an add-on. Its file will be signed, its status updated to "public"
    and it will become available through :ref:`add-ons search <addon-search-label>`.

    **Response**

    :status 202: successfully published.
    :status 403: not allowed to access this object.
    :status 404: add-on not found in the review queue.

.. http:post:: /api/v2/extensions/queue/(int:id)|(string:slug)/reject/

    Reject an add-on. Its status will be updated to "rejected". The developer
    will have to re-submit it once they fix the issues.

    .. warning::

        Since versioning and re-submitting a rejected add-on are not defined yet,
        developers have no way of submitting back for review a rejected add-on.

    **Request**

    :param comment: a comment from the reviewer
    :type comment: string

    **Response**

    :status 202: successfully published.
    :status 403: not allowed to access this object.
    :status 404: add-on not found in the review queue.
