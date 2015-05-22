.. _payment:

========
Payments
========

This API is specific to setting up and processing payments for an app in the
Marketplace.

.. _payment-account-label:

Configuring payment accounts
============================

Payment accounts can be added and listed.

.. note:: Authentication is required.

.. http:post:: /api/v2/payments/account/

    **Request**

    :param account_name: Account name.
    :type account_name: string
    :param companyName: Company name.
    :type companyName: string
    :param vendorName: Vendor name.
    :type vendorName: string
    :param financeEmailAddress: Financial email.
    :type financeEmailAddress: string
    :param supportEmailAddress: Support email.
    :type supportEmailAddress: string
    :param address1: Address.
    :type address1: string
    :param address2: Second line of address.
    :type address2: string
    :param addressCity: City/municipality.
    :type addressCity: string
    :param addressState: State/province/region.
    :type addressState: string
    :param addressZipCode: Zip/postal code.
    :type addressZipCode: string
    :param countryIso: Country.
    :type countryIso: string
    :param vatNumber: VAT number.
    :type vatNumber: string

    *the following fields cannot be modified after account creation*

    :param bankAccountPayeeName: Account holder name.
    :type bankAccountPayeeName: string
    :param bankAccountNumber: Bank account number.
    :type bankAccountNumber: string
    :param bankAccountCode: Bank account code.
    :type bankAccountCode: string
    :param bankName: Bank name.
    :param bankAddress1: Bank address.
    :type bankAddress1: string
    :param bankAddress2: Second line of bank address.
    :type bankAddress2: string
    :param bankAddressState: Bank state/province/region.
    :type bankAddressState: string
    :param bankAddressZipCode: Bank zip/postal code.
    :type bankAddressZipCode: string
    :param bankAddressIso: Bank country.
    :type bankAddressIso: string
    :param adminEmailAddress: Administrative email.
    :type adminEmailAddress: string
    :param currencyIso: Currency you prefer to be paid in.
    :type currencyIso: string

    **Response**

    :status: 201 successfully created.

.. http:put:: /api/v2/payments/account/(int:id)/

    **Request**

    :param account_name: Account name.
    :type  account_name: string
    :param vendorName: Vendor name.
    :type vendorName: string
    :param financeEmailAddress: Financial email.
    :type financeEmailAddress: string
    :param supportEmailAddress: Support email.
    :type supportEmailAddress: string
    :param address1: Address.
    :type address1: string
    :param address2: Second line of address.
    :type address2: string
    :param addressCity: City/municipality.
    :type addressCity: string
    :param addressState: State/province/region.
    :type addressState: string
    :param addressZipCode: Zip/postal code.
    :type addressZipCode: string
    :param countryIso: Country.
    :type countryIso: string
    :param vatNumber: VAT number.
    :type vatNumber: string

    **Response**

    :status 204: successfully updated.

.. http:delete:: /api/v2/payments/account/(int:id)/

    .. warning:: This can potentially remove all your apps from sale.

    If you delete a payment account then all apps which use that account can
    no longer process payments. All apps that use this payment account will
    be moved into the incomplete state. Each of those apps will need to
    resubmitted to process payments.

    **Response**

    :status 204: successfully deleted.
    :status 409: shared accounts cannot be deleted whilst apps are using them.

.. http:get:: /api/v2/payments/account/

    **Request**

    The standard :ref:`list-query-params-label`.

    **Response**

    :param meta: :ref:`meta-response-label`.
    :type meta: object
    :param objects: A :ref:`listing <objects-response-label>` of :ref:`accounts <payment-account-response-label>`.
    :type objects: array

.. _payment-account-response-label:

.. http:get:: /api/v2/payments/account/(int:id)/

    **Response**

    An account object, see below for an example.

    :status 200: successfully completed.

    Example:

    .. code-block:: json

        {
             "account_name": "account",
             "address1": "123 Main St",
             "addressCity": "Byteville",
             "addressPhone": "605-555-1212",
             "addressState": "HX",
             "addressZipCode": "55555",
             "adminEmailAddress": "apps_admin@example.com",
             "companyName": "Example Company",
             "countryIso": "BRA",
             "currencyIso": "EUR",
             "financeEmailAddress": "apps_accounts@example.com",
             "resource_uri": "/api/v2/payments/account/175/",
             "supportEmailAddress": "apps_support@example.com",
             "vendorName": "vendor"
        }

Upsell
======

.. http:post:: /api/v2/payments/upsell/

    Creates an upsell relationship between two apps, a free and premium one.
    Send the URLs for both apps in the post to create the relationship.

    **Request**

    :param free: URL to the free app.
    :type free: string
    :param premium: URL to the premium app.
    :type premium: string

    **Response**

    :status 201: sucessfully created.

.. _upsell-response-label:

.. http:get:: /api/v2/payments/upsell/(int:id)/

    **Response**

    .. code-block:: json

        {"free": "/api/v2/apps/app/1/",
         "premium": "/api/v2/apps/app/2/"}

    :param free: URL to the free app.
    :type free: string
    :param premium: URL to the premium app.
    :type premium: string

.. http:patch:: /api/v2/payments/upsell/(int:id)/

    Alter the upsell from free to premium by passing in new free and premiums.

    **Request**

    :param free: URL to the free app.
    :type free: string
    :param premium: URL to the premium app.
    :type premium: string

    **Response**

    :status 200: sucessfully altered.

.. http:delete:: /api/v2/payments/upsell/(int:id)/

    To delete the upsell relationship.

    **Response**

    :status 204: sucessfully deleted.


In-app products
===============

In-app products are used for setting up in-app payments without the need to
host your own JWT signer. This API is for managing your in-app products for use
with the in-app payment service.

The **origin** refers to the
`origin <https://developer.mozilla.org/en-US/Apps/Build/Manifest#origin>`_ of the
packaged app. For example: ``app://foo-app.com``.

.. note:: Feature not complete.

.. http:post:: /api/v2/payments/(string:origin)/in-app/

    .. note:: Authentication is required.

    Creates a new in-app product for sale.

    **Request**

    :param name:

        Product names as an object of localizations, serialized to JSON.
        Example::

            {"en-us": "English product name",
             "pl": "polska nazwa produktu"}

        The object keys must be lower case codes in the
        `IETF language tag`_ format.

    :type name: string
    :param logo_url: URL to a logo for the product.
    :type logo_url: string
    :param price_id: ID for the :ref:`price tier <price-tiers>`.
    :type price_id: int

    **Response**

    :status 201: successfully created.
    :param guid: A globally unique ID for this in-app product.
    :type guid: string
    :param app: The slug for the app.
    :type app: string
    :param name: The name for the in-app product.
    :type name: string
    :param logo_url: URL to a logo for the product.
    :type logo_url: string
    :param price_id: ID for the :ref:`price tier <price-tiers>`.
    :type price_id: int

.. http:get:: /api/v2/payments/(string:origin)/in-app/

    List the in-app products for this app.

    **Request**

    None

    **Response**

    :status 200: successfully completed.
    :param guid: The in-app product ID.
    :type guid: string
    :param app: The slug for the app.
    :type app: string
    :param name: The name for the in-app product.
    :type name: string
    :param logo_url: URL to a logo for the product.
    :type logo_url: string
    :param price_id: ID for the :ref:`price tier <price-tiers>`.
    :type price_id: int

.. http:get:: /api/v2/payments/(string:origin)/in-app/(string:id)/

    Details of an in-app product.

    **Request**

    :param active: include active products, if ignored all in-app products are
        returned. Value should be one of `0` or `1`.
    :type active: string

    **Response**

    :status 200: successfully completed.
    :param guid: The in-app product ID.
    :type guid: string
    :param app: The slug for the app.
    :type app: string
    :param name: The name for the in-app product.
    :type name: string
    :param logo_url: URL to a logo for the product.
    :type logo_url: string
    :param price_id: ID for the :ref:`price tier <price-tiers>`.
    :type price_id: int

.. http:put:: /api/v2/payments/(string:origin)/in-app/(string:id)/

    .. note:: Authentication is required.

    Update an in-app product.

    **Request**

    :param name:

        Product names as an object of localizations, serialized to JSON.
        Example::

            {"en-us": "English product name",
             "pl": "polska nazwa produktu"}

        The object keys must be lower case codes in the
        `IETF language tag`_ format.

        **IMPORTANT**: Any string for a new locale will not
        overwrite strings in existing locales. If you want
        to delete an older locale, you need to set it to ``null``
        like ``{"en-us": null, "pl": "..."}``.

    :type name: string
    :param logo_url: URL to a logo for the product.
    :type logo_url: string
    :param price_id: ID for the :ref:`price tier <price-tiers>`.
    :type price_id: int

    **Response**

    :status 200: successfully completed.
    :param guid: The in-app product ID.
    :type guid: string
    :param app: The slug for the app.
    :type app: string
    :param name: The name for the in-app product.
    :type name: string
    :param logo_url: URL to a logo for the product.
    :type logo_url: string
    :param price_id: ID for the :ref:`price tier <price-tiers>`.
    :type price_id: int

.. http:get:: /api/v2/payments/stub-in-app-products/

    List some stub in-app products that can be used for testing.
    These products can only be purchased in simulation mode.

    **Request**

    None

    **Response**

    .. code-block:: json

        {
            "meta": {
                "limit": 25,
                "next": null,
                "offset": 0,
                "previous": null,
                "total_count": 2
            },
            "objects": [
                {
                    "app": null,
                    "guid": "d3182953-feed-44dd-a3be-e17ae7fe6a2c",
                    "logo_url": "https://marketplace.cdn.mozilla.net/media/img/developers/simulated-kiwi.png",
                    "name": "Kiwi",
                    "price_id": 237
                },
                {
                    "app": null,
                    "guid": "8b3fa156-354a-47a9-b862-0f02b56d0e3d",
                    "logo_url": "https://marketplace.cdn.mozilla.net/media/img/mkt/icons/rocket-64.png",
                    "name": "Rocket",
                    "price_id": 238
                }
            ]
        }

    :status 200: successfully completed.
    :objects: list of stub products.
        See :ref:`get stub product <get-stub-product>`.

.. _get-stub-product:

.. http:get:: /api/v2/payments/stub-in-app-products/(string:guid)/

    Get detailed info for a specific stub product.

    **Request**

    None

    **Response**

    :status 200: successfully completed.
    :param guid: The in-app product ID.
    :type guid: string
    :param name: The name for the in-app product.
    :type name: string
    :param logo_url: URL to a logo for the product.
    :type logo_url: string
    :param price_id: ID for the :ref:`price tier <price-tiers>`.
    :type price_id: int

.. _`IETF language tag`: http://en.wikipedia.org/wiki/IETF_language_tag


Preparing payment
=================

Produces the JWT for purchasing an app that is passed to `navigator.mozPay`_.

.. note:: Authentication is required.

.. http:post:: /api/v2/webpay/prepare/

    **Request**

    :param string app: the id or slug of the app to be purchased.

    **Response**

    .. code-block:: json

        {
            "app": "337141: Something Something Steamcube!",
            "contribStatusURL": "https://marketplace.firefox.com/api/v2/webpay/status/123/",
            "resource_uri": "",
            "webpayJWT": "eyJhbGciOiAiSFMy... [truncated]",
        }

    :param webpayJWT: the JWT to pass to `navigator.mozPay`_
    :type webpayJWT: string
    :param contribStatusURL: the URL to poll for
        :ref:`payment-status-label`.
    :type contribStatusURL: string

    :status 201: successfully completed.
    :status 400: app not found.
    :status 401: not authenticated.
    :status 403: app cannot be purchased.
    :status 409: app already purchased.


Produces the JWT for purchasing an in-app product that is passed to `navigator.mozPay`_.

.. note:: Feature not complete.

.. note:: Authentication is not required or supported.

.. http:post:: /api/v2/webpay/inapp/prepare/

    **Request**

    :param string inapp: the guid the in-app product to be purchased.

    **Response**

    .. code-block:: json

        {
            "contribStatusURL": "https://marketplace.firefox.com/api/v2/webpay/status/123/",
            "webpayJWT": "eyJhbGciOiAiSFMy... [truncated]",
        }

    :param webpayJWT: the JWT to pass to `navigator.mozPay`_
    :type webpayJWT: string
    :param contribStatusURL: the URL to poll for
        :ref:`payment-status-label`.
    :type contribStatusURL: string

    :status 201: successfully completed.
    :status 400: in-app product not found.


Signature Check
===============

Retrieve a JWT that can be used to check the signature for making payments.
This is intended for system health checks and requires no authorization.
You can pass the retrieved JWT to the `WebPay`_ API to verify its signature.

.. http:post:: /api/v2/webpay/sig_check/

    **Request**

    No parameters are necessary.

    **Response**

    .. code-block:: json

        {
            "sig_check_jwt": "eyJhbGciOiAiSFMyNT...XsgG6JKCSw"
        }

    :param sig_check_jwt: a JWT that can be passed to `WebPay`_.
    :type sig_check_jwt: string

    :status 201: successfully created resource.

.. _payment-status-label:

Payment status
==============

.. http:get:: /api/v2/webpay/status/(string:uuid)/

    **Request**

    :param uuid: the uuid of the payment. This URL is returned as the
        ``contribStatusURL`` parameter of a call to *prepare*.
    :type uuid: string

    **Response**

    :param status: ``complete`` or ``incomplete``
    :type status: string
    :param receipt: for in-app purchases only, a `Web application receipt`_
    :type status: string

    Example:

    .. code:: json

        {"status": "complete",
         "receipt": null}

    In-app purchases will include a receipt:

    .. code:: json

        {"status": "complete",
         "receipt": "eyJhbGciOiAiUlM1MTI...0Xg0EQfUfH121U7b_tqAYaY"}

    :status 200: request processed, check status for value.

.. _`Web application receipt`: https://wiki.mozilla.org/Apps/WebApplicationReceipt

Installing
==========

When an app is installed from the Marketplace, call the install API. This will
record the install.

Free apps
---------

.. http:post:: /api/v2/installs/record/

    **Request**:

    :param app: the id or slug of the app being installed.
    :type app: int|string

    **Response**:

    :status 201: successfully completed.
    :status 202: an install was already recorded for this user and app, so
        we didn't bother creating another one.
    :status 403: app is not public, install not allowed.


Premium apps
------------

.. note:: Authentication is required.

.. http:post:: /api/v2/receipts/install/

    Returns a receipt if the app is paid and a receipt should be installed.

    **Request**:

    :param app: the id or slug of the app being installed.
    :type app: int|string

    **Response**:

    .. code-block:: json

        {"receipt": "eyJhbGciOiAiUlM1MT...[truncated]"}

    :status 201: successfully completed.
    :status 401: not authenticated.
    :status 402: payment required.
    :status 403: app is not public, install not allowed.

Developers
~~~~~~~~~~

Developers of the app will get a special developer receipt that is valid for
24 hours and does not require payment. See also `Test Receipts`_.

.. _`Test Receipts`: https://developer.mozilla.org/en-US/Marketplace/Monetization/Validating_a_receipt#Test_receipts

Reviewers
~~~~~~~~~

Reviewers should not use this API.

Receipt Testing
===============

Returns test receipts for use during testing or development. The returned
receipt will have type `test-receipt`. Only works for hosted apps.

.. http:post:: /api/v2/receipts/test/

    Returns a receipt suitable for testing your app.

    **Request**:

    :param manifest_url: the fully qualified URL to the manifest, including
        protocol.
    :type manifest_url: string
    :param receipt_type: one of ``ok``, ``expired``, ``invalid`` or ``refunded``.
    :type receipt_type: string

    **Response**:

    .. code-block:: json

        {"receipt": "eyJhbGciOiAiUlM1MT...[truncated]"}

    :status 201: successfully completed.

Receipt reissue
===============

Takes an expired receipt and returns a reissued receipt with updated expiry
times.

.. http:post:: /api/v2/receipts/reissue/

    **Request**

    :param: the body of the request must contain the receipt, in the same way
        that the `receipt verification`_ endpoint does.

    **Response**:

    For a good response:

    .. code-block:: json

        {
            "reason": "",
            "receipt": "eyJhbGciOiAiUlM1MT...[truncated]",
            "status": "expired"
        }

    For a failed response:

    .. code-block:: json

        {
            "reason": "NO_PURCHASE",
            "receipt": "",
            "status": "invalid"
        }

    :param reason: only present if the request failed, contains the reason
        for failure, see `receipt verification`_ docs.
    :type reason: string
    :param receipt: the receipt, currently blank.
    :type receipt: string
    :param status: one of ``ok``, ``expired``, ``invalid``, ``pending``,
        ``refunded``
    :type status: string

    :status 200: successfully completed.
    :status 400: the receipt was not valid or not in an expired state, examine
        the response to see the cause. The messages and the causes are the
        same as for `receipt verification`_.

.. _price-tiers:


Price Tiers
===========

.. http:get:: /api/v2/webpay/prices/

    Gets a list of pay tiers from the Marketplace.

    **Request**

    :param provider: (optional) the payment provider. Current values: *bango*
    :type provider: string

    The standard :ref:`list-query-params-label`.

    **Response**

    :param meta: :ref:`meta-response-label`.
    :type meta: object
    :param objects: A :ref:`listing <objects-response-label>` of :ref:`pay tiers <pay-tier-response-label>`.
    :type objects: array
    :status 200: successfully completed.

.. _pay-tier-response-label:

.. http:get:: /api/v2/webpay/prices/(int:id)/

    Returns a specific pay tier.

    **Response**

    .. code-block:: json

        {
            "name": "Tier 1",
            "pricePoint": "1",
            "prices": [{
                "price": "0.99",
                "method": 2,
                "region": 2,
                "tier": 26,
                "provider": 1,
                "currency": "USD",
                "id": 1225,
                "dev": true,
                "paid": true
            }, {
                "price": "0.69",
                "method": 2,
                "region": 14,
                "tier": 26,
                "provider": 1,
                "currency": "DE",
                "id": 1226,
                "dev": true,
                "paid": true
            }],
            "localized": {},
            "resource_uri": "/api/v2/webpay/prices/1/",
            "created": "2011-09-29T14:15:08",
            "modified": "2013-05-02T14:43:58"
        }

    :param region: a :ref:`region <region-response-label>`.
    :type region: int
    :param carrier: a :ref:`carrier <carrier-response-label>`.
    :type carrier: int
    :param localized: see `Localized tier`.
    :type localized: object
    :param tier: the id of the tier.
    :type tier: int
    :param method: the :ref:`payment method <payment-methods-label>`.
    :type method: int
    :param provider: the :ref:`payment provider <provider-label>`.
    :type provider: int
    :param pricePoint: this is the value used for in-app payments.
    :type pricePoint: string
    :param dev: if ``true`` the tier will be shown to the developer during
        app configuration.
    :type dev: boolean
    :param paid: if ``true`` this tier can be used for payments by users.
    :type paid: boolean
    :status 200: successfully completed.

.. _payment-methods-label:

Payment methods:

* ``0`` Carrier billing only
* ``1`` Credit card only
* ``2`` Both carrier billing and credit card

.. _provider-label:

Provider:

* ``0`` Paypal, not currently supported
* ``1`` Bango
* ``2`` `Reference implementation`_, not currently supported outside of
  development instances
* ``3`` Boku

.. _localized-tier-label:

Localized tier
--------------

To display a price to your user, it would be nice to know how to display a
price in the app. The Marketplace does some basic work to calculate the locale
of a user. Information that would be useful to show to your user is placed in
the localized field of the result.

A request with the HTTP *Accept-Language* header set to *pt-BR*, means that
*localized* will contain:

    .. code-block:: json

        {
            "localized": {
                "amount": "10.00",
                "currency": "BRL",
                "locale": "R$10,00",
                "region": "Brasil"
            }
        }

The exact same request with an *Accept-Language* header set to *en-US*
returns:

    .. code-block:: json

        {
            "localized": {
                "amount": "0.99",
                "currency": "USD",
                "locale": "$0.99",
                "region": "United States"
            }
        }

If a suitable currency for the region given in the request cannot be found, the
result will be empty. It could be that the currency that the Marketplace will
accept is not the currency of the country. For example, a request with
*Accept-Language* set to *fr* may result in:

    .. code-block:: json

        {
            "localized": {
                "amount": "1.00",
                "currency": "USD",
                "locale": "1,00\xa0$US",
                "region": "Monde entier"
            }
        }

Please note: these are just examples to demonstrate cases. Actual results will
vary depending upon data sent and payment methods in the Marketplace.

Product Icons
=============

Authenticated clients like `WebPay`_ need to display external product images in a
safe way. This API lets WebPay cache and later retrieve icon URLs.

.. note:: All write requests (``POST``, ``PATCH``) require authenticated users to have the
    ``ProductIcon:Create``  permission.


.. http:get:: /api/v2/webpay/product/icon/

    Gets a list of cached product icons.

    **Request**

    :param ext_url: Absolute external URL of product icon that was cached.
    :type ext_url: string
    :param ext_size: Height and width pixel value that was declared for this icon.
    :type ext_size: int
    :param size: Height and width pixel value that this icon was resized to.

    You may also request :ref:`list-query-params-label`.

    **Response**

    :param meta: :ref:`meta-response-label`.
    :type meta: object
    :param objects: A :ref:`listing <objects-response-label>` of :ref:`product icons <product-icon-response-label>`.
    :type objects: array
    :status 200: successfully completed.

.. _product-icon-response-label:

.. http:get:: /api/v2/webpay/product/icon/(int:id)/

    **Response**

    .. code-block:: json

        {
            "url": "http://marketplace-cdn/product-icons/0/1.png",
            "resource_uri": "/api/v2/webpay/product/icon/1/",
            "ext_url": "http://appserver/media/icon.png",
            "ext_size": 64,
            "size": 64
        }

    :param url: Absolute URL of the cached product icon.
    :type url: string
    :status 200: successfully completed.

.. http:post:: /api/v2/webpay/product/icon/

    Post a new product icon URL that should be cached.
    This schedules an icon to be processed but does not return any object data.

    **Request**

    :param ext_url: Absolute external URL of product icon that should be cached.
    :type ext_url: string
    :param ext_size: Height and width pixel value that was declared for this icon.
    :type ext_size: int
    :param size: Height and width pixel value that this icon should be resized to.
    :type size: int

    **Response**

    :status 202: New icon accepted. Deferred processing will begin.
    :status 400: Some required fields were missing or invalid.
    :status 401: The API user is unauthorized to cache product icons.


Transaction failure
===================

.. note:: Requires authenticated users to have the Transaction:NotifyFailure
    permission. This API is used by internal clients such as WebPay_.

.. http:patch:: /api/v2/webpay/failure/(int:transaction_id)/

    Notify the app developers that our attempts to call the postback or
    chargebacks URLs from `In-app Payments`_ failed. This will send an
    email to the app developers.

    **Response**

    :status 202: Notification will be sent.
    :status 403: The API user is not authorized to report failures.

.. _CORS: https://developer.mozilla.org/en-US/docs/HTTP/Access_control_CORS
.. _WebPay: https://github.com/mozilla/webpay
.. _In-app Payments: https://developer.mozilla.org/en-US/docs/Apps/Publishing/In-app_payments
.. _navigator.mozPay: https://wiki.mozilla.org/WebAPI/WebPayment
.. _Reference Implementation: http://zippypayments.readthedocs.org/en/latest/
.. _receipt verification: https://wiki.mozilla.org/Apps/WebApplicationReceipt#Interaction_with_the_verify_URL
