.. _validation:

Validation
==========

.. note:: The validation does not require you to be authenticated, however you
    cannot create apps from those validations. To validate and then submit an
    app you must be authenticated with the same account for both steps.

.. _validation-post-label:

.. http:post:: /api/v2/apps/validation/

    **Request**

    For an `Hosted App <https://developer.mozilla.org/en-US/Marketplace/Options/Hosted_apps>`_:

    :param manifest: URL to the manifest.
    :type manifest: string

    Example:

    .. code-block:: json

        {"manifest": "http://test.app.com/manifest.webapp"}

    Or for a `Packaged App <https://developer.mozilla.org/en-US/Marketplace/Options/Packaged_apps>`_:

    :param upload: an object containing the appropriate file data in the upload field. It has the following properties:
    :type upload: object
    :param upload.type: the content type for the file. In this case, the only valid type is `application/zip`.
    :type upload.type: string
    :param upload.data: the zip file for your app, encoded in base 64.
    :type upload.data: string
    :param upload.name: the file name.
    :type upload.name: string

    Example:

    .. code-block:: json

        {"upload": {"type": "application/zip",
                    "data": "UEsDBAo...gAAAAA=",
                    "name": "mozball.zip"}}

    **Response**

    Returns a :ref:`validation <validation-response-label>` result.

    :status 201: successfully created, processed.
    :status 202: successfully created, still processing.

.. _validation-response-label:

.. http:get:: /api/v2/apps/validation/(string:id)/

    **Response**

    Returns a particular validation. You should poll this API to it returns
    a processed result before moving on with the submission process.

    :param id: the id of the validation.
    :type id: string
    :param processed: if the validation has been processed. Hosted apps are
        done immediately but packaged apps are queued. Clients will have to
        poll the results URL until the validation has been processed.
    :type processed: boolean
    :param valid: if the validation passed.
    :type valid: boolean
    :param validation: the resulting validation messages if it failed.
    :type validation: string
    :status 200: successfully completed.

    Example not processed:

    .. code-block:: json

        {
            "id": "123abcd",
            "processed": false,
            "resource_uri": "/api/v2/apps/validation/123abcd/",
            "valid": false,
            "validation": ""
        }

    Example processed and passed:

    .. code-block:: json

        {
            "id": "123abcd",
            "processed": true,
            "resource_uri": "/api/v2/apps/validation/123abcd/",
            "valid": true,
            "validation": ""
        }

    Example processed and failed:

    .. code-block:: json

        {
            "id": "123abcd",
            "processed": true,
            "resource_uri": "/api/v2/apps/validation/123abcd/",
            "valid": false,
            "validation": {
            "errors": 1, "messages": [{
                "tier": 1,
                "message": "Your manifest must be served with the HTTP header \"Content-Type: application/x-web-app-manifest+json\". We saw \"text/html; charset=utf-8\".",
                "type": "error"
            }],
        }
