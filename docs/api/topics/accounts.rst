.. _accounts:

========
Accounts
========

User accounts on the Firefox Marketplace.

Account
=======

.. note:: Requires authentication.

The account API, makes use of the term ``mine``. This is an explicit variable to
lookup the logged in user account id.

.. http:get:: /api/v2/account/settings/mine/

    Returns data on the currently logged in user.

    **Response**

    .. code-block:: json

        {
            "resource_uri": "/api/v2/account/settings/1/",
            "display_name": "Nice person",
            "enable_recommendations": true
        }

To update account information:

.. http:patch:: /api/v2/account/settings/mine/

    **Request**

    :param display_name: the displayed name for this user.
    :type display_name: string
    :param enable_recommendations: whether to show app recommendations or not.
    :type enable_recommendations: boolean

    **Response**

    No content is returned in the response.

    :status 200: successfully completed.

Fields that can be updated:

* *display_name*
* *enable_recommendations*

.. http:get:: /api/v2/account/installed/mine/

    Returns a list of the installed apps for the currently logged in user. This
    ignores any reviewer or developer installed apps.

    **Request**

    The standard :ref:`list-query-params-label`.

    **Response**

    :param meta: :ref:`meta-response-label`.
    :type meta: object
    :param objects: A :ref:`listing <objects-response-label>` of :ref:`apps <app-response-label>`.
    :type objects: array
    :status 200: sucessfully completed.

.. http:post:: /api/v2/account/installed/mine/remove_app/

    Removes an app from the list of the installed apps for the currently logged
    in user. This only works for user installed apps.

    **Request**

    :param app: the app id
    :type app: int

    **Response**

    :status 202: sucessfully completed.

.. _permission-get-label:

.. http:get:: /api/v2/account/permissions/mine/

    Returns a mapping of the permissions for the currently logged in user.

    **Response**

    .. code-block:: json

        {
            "permissions": {
                "admin": false,
                "curator": false,
                "developer": false,
                "localizer": false,
                "lookup": true,
                "revenue_stats": false,
                "reviewer": false,
                "stats": false,
                "webpay": false
            },
            "resource_uri": "/api/v2/account/permissions/1/"
        }

    :param permissions: permissions and properties for the user account. It
        contains boolean values which describe whether the user has the
        permission described by the key of the field.
    :type permissions: object
    :status 200: sucessfully completed.

Feedback
========

.. http:post:: /api/v2/account/feedback/

    Submit feedback to the Marketplace.

    .. note:: Authentication is optional.

    .. note:: This endpoint is rate-limited at 30 requests per hour per user.

    **Request**

    :param chromeless: (optional) "Yes" or "No", indicating whether the user
                       agent sending the feedback is chromeless.
    :type chromeless: string
    :param feedback: (required) the text of the feedback.
    :type feedback: string
    :param from_url: (optional) the URL from which the feedback was sent.
    :type from_url: string
    :param platform: (optional) a description of the platform from which the
                     feedback is being sent.
    :type platform: string

    .. code-block:: json

        {
            "chromeless": "No",
            "feedback": "Here's what I really think.",
            "platform": "Desktop",
            "from_url": "/feedback",
            "sprout": "potato"
        }

    This form uses `PotatoCaptcha`, so there must be a field named `sprout` with
    the value `potato` and cannot be a field named `tuber` with a truthy value.

    **Response**

    .. code-block:: json

        {
            "chromeless": "No",
            "feedback": "Here's what I really think.",
            "from_url": "/feedback",
            "platform": "Desktop",
            "user": null,
        }

    :status 201: successfully completed.
    :status 429: exceeded rate limit.

Newsletter signup
=================

.. http:post:: /api/v2/account/newsletter/

    This resource requests that the email passed in the request parameters be
    subscribed to the Marketplace newsletter.

    .. note:: Authentication is optional.

    .. note:: This endpoint is rate-limited at 30 requests per hour per user/IP.

   **Request**

   :param email: The email address to send newsletters to.
   :type email: string
   :param newsletter: The newsletter to subscribe to. Can be either 'marketplace'
                      or 'about:apps'.
   :type newsletter: string

   **Response**

   :status 204: Successfully signed up.
   :status 429: exceeded rate limit.


Operator Permissions
====================

Users may be granted permission to operate as an administrator on individual
carrier/region pairs.

.. http:get:: /api/v2/account/operators/

    Return a list of each carrier/region pair upon which the user has permission
    to operate.

    .. note:: Authentication is optional, but unauthenticated requests will never
        return data.

    **Response**

    :param meta: :ref:`meta-response-label`.
    :type meta: object
    :param objects: A list of carrier/region pairs for the user.
    :type objects: array

    .. code-block:: json

        [
            {
                'carrier': 'telefonica',
                'region': 'br'
            },
            {
                'carrier': 'telefonica',
                'region': 'co'
            }
        ]

    If the user is able to administer every carrier/region pair, it will
    instead return:

    .. code-block:: json

        [
            '*'
        ]


Sign Developer Agreement
========================

.. _show-agreement:

.. http:post:: /api/v2/account/dev-agreement/show/

    Get the developer agreement URL for the authenticating user.

    .. note:: Authentication is required.

    **Response**

    :status 200: successfully viewed developer agreement.
    :status 201: successfully viewed developer agreement for the first time.
      The user can now :ref:`sign the agreement <read-agreement>`.
    :status 400: user has already signed terms of service.
    :status 403: authentication required.
    :status 405: invalid HTTP method; only POST is allowed on this endpoint.

.. read-agreement:

.. http:post:: /api/v2/account/dev-agreement/read/

    Sign the developer agreement for the authenticating user. The user must
    have already :ref:`been shown <show-agreement>` the developer agreement

    .. note:: Authentication is required.

    **Response**

    :status 201: successfully signed.
    :status 400: user has already signed terms of service.
    :status 403: authentication required.
    :status 405: invalid HTTP method; only POST is allowed on this endpoint.
