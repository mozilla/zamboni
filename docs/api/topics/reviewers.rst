.. _reviewers:

=========
Reviewers
=========

Reviewer API provides access to the reviewer tools.

Reviewer Search
===============

.. note:: Requires authentication and permission to review apps.

.. http:get::  /api/v2/reviewers/search/

    Performs a search just like the regular Search API, but customized with
    extra parameters and different (smaller) apps objects returned, containing
    only the information that is required for reviewer tools.

    **Response**:

    :param meta: :ref:`meta-response-label`.
    :type meta: object
    :param objects: A :ref:`listing <objects-response-label>` of :ref:`apps <reviewers-app-response-label>`.
    :type objects: array

    :status 200: successfully completed.

    .. _reviewers-app-response-label:

    Each app in the response will contain the following:

    :param device_types: a list of the device types at least one of:
        `desktop`, `mobile`, `tablet`, `firefoxos`. `mobile` and `tablet` both
        refer to Android mobile and tablet. As opposed to Firefox OS.
    :type device_types: array
    :param id: the app's id.
    :type id: int
    :param is_escalated: a boolean indicating whether this app is currently
        in the escalation queue or not.
    :type is_escalated: boolean
    :param is_packaged: a boolean indicating whether the app is packaged or
        not.
    :type is_packaged: boolean
    :param latest_version: an array containing the following information about
        the app's latest version:
    :type latest_version: object
    :param latest_version.has_editor_comment: a boolean indicathing whether
        that version contains comments from a reviewer.
    :type latest_version.has_editor_comment: boolean
    :param latest_version.has_info_request: a boolean indicathing whether that
        version contains an information request from a reviewer.
    :type latest_version.has_info_request: boolean
    :param latest_version.is_privileged: a boolean indicating whether this
        version is a privileged app or not.
    :type latest_version.is_privileged: boolean
    :param latest_version.status: an int representing the version status. Can
        be different from the app status, since the latest_version can be
        different from the latest public one.
    :type latest_version.status: int
    :param name: the name of the app
    :type name: string
    :param premium_type: one of ``free``, ``premium``, ``free-inapp``,
        ``premium-inapp``. If ``premium`` or ``premium-inapp`` the app should
        be bought, check the ``price`` field to determine if it can.
    :type premium_type: string
    :param price: If it is a paid app this will be a string representing
        the price in the currency calculated for the request. If ``0.00`` then
        no payment is required, but the app requires a receipt. If ``null``, a
        price cannot be calculated for the region and cannot be bought.
        Example: 1.00
    :type price: string|null
    :param name: the URL slug for the app
    :type name: string
    :param status: an int representing the version status.
    :type latest_version.status: int


Reviewing
=========

.. note:: Requires authentication and permission to review apps.

.. warning:: Not available through CORS.

.. http:get::  /api/v2/reviewers/reviewing/

    Returns a list of apps that are being reviewed.

    **Response**:

    :param meta: :ref:`meta-response-label`.
    :type meta: object
    :param objects: A :ref:`listing <objects-response-label>` of :ref:`apps <app-response-label>`.
    :type objects: array

    :status 200: successfully completed.


Mini-Manifest
=============

.. note:: Requires authentication and permission to review apps.

.. warning:: Not available through CORS.

.. http:post::  /api/v2/reviewers/app/(int:id)|(string:slug)/token

    Returns a short-lived token that can be used to access the
    mini-manifest. Use this token as a query-string parameter to the
    mini-manifest URL named "token" within 60 seconds.

    **Response**:

    :param token: The token.
    :type meta: string

    :status 200: successfully completed.


Canned Responses
================

.. note:: Requires authentication and permission to alter reviewer tools.

.. http:get::  /api/v1/reviewers/canned-responses/
.. http:post::  /api/v1/reviewers/canned-responses/
.. http:get::  /api/v1/reviewers/canned-responses/(int:id)/
.. http:put::  /api/v1/reviewers/canned-responses/(int:id)/
.. http:patch::  /api/v1/reviewers/canned-responses/(int:id)/
.. http:delete::  /api/v1/reviewers/canned-responses/(int:id)/


    Return, create, modify and delete the canned responses reviewers can use
    when reviewing apps.

    **Response / Request parameters**:

    :param id: unique identifier for the canned response.
    :type id: int
    :param name: canned response name.
    :type name: string|object|null
    :param response: canned response text.
    :type response: string|object|null
    :param sort_group: group the canned response belongs to.
    :type sort_group: string

    :status 200: successfully completed.
    :status 201: successfully created.
    :status 204: successfully deleted.
    :status 400: error processing the request.
    :status 404: not found.


Reviewer Scores
===============

.. note:: Requires authentication and permission to alter reviewer tools.

.. http:get::  /api/v1/reviewers/scores/
.. http:post::  /api/v1/reviewers/scores/
.. http:get::  /api/v1/reviewers/scores/(int:id)/
.. http:put::  /api/v1/reviewers/scores/(int:id)/
.. http:patch::  /api/v1/reviewers/scores/(int:id)/
.. http:delete::  /api/v1/reviewers/scores/(int:id)/


    Return, create, modify and delete the reviewer scores for an user. This API
    only deals with manual scores, and never returns or allows you to modify
    automatic ones.

    **Response / Request parameters**:

    :param id: unique identifier for the reviewer score.
    :type id: int
    :param score: score value (can be negative).
    :type score: int
    :param note: optional note attached to the score.
    :type note: string

    :status 200: successfully completed.
    :status 201: successfully created.
    :status 204: successfully deleted.
    :status 400: error processing the request.
    :status 404: not found.
