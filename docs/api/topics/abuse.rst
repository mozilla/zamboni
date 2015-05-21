.. _abuse:

===================
Abuse and reporting
===================

Abusive apps, users and websites may be reported to Marketplace staff. It can
also be used to signal issues about the corresponding listing on Marketplace.

    .. note:: Authentication is optional for abuse reports.

    .. note:: These endpoints are rate-limited at 30 requests per hour per user.


Report An Abusive App
=====================

.. http:post:: /api/v2/abuse/app/

    Report an abusive app to Marketplace staff.

    **Request**

    :param text: a textual description of the abuse
    :type text: string
    :param app: the app id or slug of the app being reported
    :type app: int|string

    .. code-block:: json

        {
            "sprout": "potato",
            "text": "There is a problem with this app.",
            "app": 2
        }

    This endpoint uses `PotatoCaptcha`, so there must be a field named `sprout`
    with the value `potato` and cannot be a field named `tuber` with a truthy
    value.

    **Response**

    .. code-block:: json

        {
            "reporter": null,
            "text": "There is a problem with this app.",
            "app": {
                "id": 2,
                "name": "cvan's app",
                "...": "more info"
            }
        }

    :status 201: successfully submitted.
    :status 400: submission error.
    :status 429: exceeded rate limit.


Report An Abusive User
======================

.. http:post:: /api/v2/abuse/user/

    Report an abusive user to Marketplace staff.

    **Request**

    :param text: a textual description of the abuse
    :type text: string
    :param user: the primary key of the user being reported
    :type user: int

    .. code-block:: json

        {
            "sprout": "potato",
            "text": "There is a problem with this user",
            "user": 27
        }

    This endpoint uses `PotatoCaptcha`, so there must be a field named `sprout`
    with the value `potato` and cannot be a field named `tuber` with a truthy
    value.

    **Response**

    .. code-block:: json

        {
            "reporter": null,
            "text": "There is a problem with this user.",
            "user": {
                "display_name": "cvan",
                "resource_uri": "/api/v2/account/settings/27/"
            }
        }

    :status 201: successfully submitted.
    :status 400: submission error.
    :status 429: exceeded rate limit.


Report A Website
================

.. http:post:: /api/v2/abuse/website/

    Report an issue with a website to Marketplace staff.

    **Request**

    :param text: a textual description of the issue
    :type text: string
    :param app: the id of the website being reported
    :type app: int

    .. code-block:: json

        {
            "sprout": "potato",
            "text": "There is a problem with this site.",
            "website": 42
        }

    This endpoint uses `PotatoCaptcha`, so there must be a field named `sprout`
    with the value `potato` and cannot be a field named `tuber` with a truthy
    value.

    **Response**

    .. code-block:: json

        {
            "reporter": null,
            "text": "There is a problem with this app.",
            "website": {
                "id": 42,
                "name": "cvan's site",
                "...": "more info"
            }
        }

    :status 201: successfully submitted.
    :status 400: submission error.
    :status 429: exceeded rate limit.
