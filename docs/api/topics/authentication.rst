.. _authentication:

==============
Authentication
==============

Not all APIs require authentication. Each API will note if it needs
authentication.

Two options for authentication are available: shared-secret and OAuth.

.. _sharedsecret:

Shared Secret
=============

The Marketplace front end uses a server-supplied token for authentication,
stored as a cookie.

Login
-----

.. http:post:: /api/v2/account/login/

    **Request**

    :param assertion: the Persona assertion.
    :type assertion: string
    :param audience: the Persona audience.
    :type audience: string

    Example:

    .. code-block:: json

        {
            "assertion": "1234",
            "audience": "some.site.com"
        }

    **Response**

    :param error: any error that occurred.
    :type error: string
    :param token: a shared secret to be used on later requests. It should be
        sent with authorized requests as a query string parameter named
        ``_user``.
    :type token: string
    :param permissions: :ref:`user permissions <permission-get-label>`.
    :type permissions: object
    :param settings: user account settings.
    :type settings: object

    Example:

    .. code-block:: json

        {
            "error": null,
            "token": "ffoob@example.com,95c9063d9f249aacfe5697fc83192e...",
            "settings": {
                "display_name": "fred foobar",
                "email": "ffoob@example.com",
                "enable_recommendations": true,
                "region": "appistan"
            },
            "permissions": {
                "reviewer": false,
                "admin": false,
                "localizer": false,
                "lookup": true,
                "developer": true
            }
        }

    :status 201: successfully completed, a new profile might have been created
        in the marketplace if the account was new.


Logout
------

.. http:delete:: /api/v2/account/logout/

    **Request**

    :param _user: the shared secret token returned from the login endpoint.
    :type _user: string

    Example:

    .. code-block:: json

        {
            "_user": "ffoob@example.com,95c9063d9f249aacfe5697fc83192e..."
        }

    **Response**

    :status 204: successfully logged out. The previously shared token is now
        unauthenticated and should be cleared from client storage.


OAuth
=====

Marketplace provides OAuth 1.0a, allowing third-party apps to interact with its
API. It provides it in two flavours: 2-legged OAuth, designed for command line
tools and 3-legged OAuth designed for web sites.

See the `OAuth Guide <http://hueniverse.com/oauth/guide/>`_ and this `authentication flow diagram <http://oauth.net/core/diagram.png>`_ for an overview of OAuth concepts.

Web sites
---------

Web sites that want to use the Marketplace API on behalf of a user should
use the 3-legged flow to get an access token per user.

When creating your API token, you should provide two extra fields used by the Marketplace when prompting users for authorization, allowing your application to make API requests on their behalf.

* `Application Name` should contain the name of your app, for Marketplace to show users when asking them for authorization.
* `Redirect URI` should contain the URI to redirect the user to, after the user grants access to your app (step D in the diagram linked above).

The OAuth URLs on the Marketplace are:

 * The Temporary Credential Request URL path is `/oauth/register/`.
 * The Resource Owner Authorization URL path is `/oauth/authorize/`.
 * The Token Request URL path is `/oauth/token/`.

Command-line tools
------------------

If you would like to use the Marketplace API from a command-line tool you don't
need to set up the full 3 legged flow. In this case you just need to sign the
request. Some discussion of this can be found `here <http://blog.nerdbank.net/2011/06/what-is-2-legged-oauth.html>`_.

Once you've created an API key and secret you can use the key and secret in
your command-line tools.

Production server
=================

The production server is at https://marketplace.firefox.com.

1. Log in using Persona:
   https://marketplace.firefox.com/login

2. At https://marketplace.firefox.com/developers/api provide the name of
   the app that will use the key, and the URI that Marketplace's OAuth provide
   will redirect to after the user grants permission to your app. You may then
   generate a key pair for use in your application.

3. (Optional) If you are planning on submitting an app, you must accept the
   terms of service: https://marketplace.firefox.com/developers/terms

Development server
==================

The development server is at https://marketplace-dev.allizom.org.

We make no guarantees on the uptime of the development server. Data is
regularly purged, causing the deletion of apps and tokens.

Using OAuth Tokens
==================

Once you've got your token, you will need to ensure that the OAuth token is
sent correctly in each request.

To correctly sign an OAuth request, you'll need the OAuth consumer key and
secret and then sign the request using your favourite OAuth library. An example
of this can be found in the `example marketplace client`_.

Example headers (new lines added for clarity)::

        Content-type: application/json
        Authorization: OAuth realm="",
                       oauth_body_hash="2jm...",
                       oauth_nonce="06731830",
                       oauth_timestamp="1344897064",
                       oauth_consumer_key="some-consumer-key",
                       oauth_signature_method="HMAC-SHA1",
                       oauth_version="1.0",
                       oauth_signature="Nb8..."

If requests are failing and returning a 401 response, then there will likely be
a reason contained in the response. For example:

        .. code-block:: json

            {"reason": "Terms of service not accepted."}

Example clients
---------------

* The `Marketplace.Python <https://github.com/mozilla/Marketplace.Python/>`_ library uses 2-legged OAuth to authenticate requests.

* `Curling <http://curling.readthedocs.org/>`_ is a command library to do requests using `Python <https://github.com/mozilla/Marketplace.Python/>`_.

.. _`example marketplace client`: https://github.com/mozilla/Marketplace.Python
