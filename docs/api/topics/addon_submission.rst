.. _addon_submission:

=================
Add-on Submission
=================

How to submit an Add-on
=======================

.. warning::

    Add-ons in Marketplace are experimental and not yet available in production.
    This API is not ready for public consumption yet and can change at any
    moment.


Like apps, submitting an addon involves a few steps. The client must be logged
in for all these steps and the user submitting the addon must have accepted the
terms of use.

1. :ref:`Validate your addon <addon_validation-post-label>`. The validation
   will return a validation id.
2. :ref:`Post your app <addon-post-label>` using the validation id.
   This will create an addon and populate the data with the
   contents of the manifest. It will return the current app data.
3. :ref:`Update your addon <addon-patch-label>` if necessary.
4. :ref:`Ask for a review <addon-status-patch-label>`. All addons need to be
   reviewed, this will add it to the review queue.

.. _addon_validation:

Addon Validation
================

.. note:: The validation API does not require you to be authenticated, however
    you cannot create addons from those validations. To validate and then
    submit an addon you must be authenticated with the same account for both
    steps.

.. _addon_validation-post-label:

.. http:post:: /api/v2/extensions/validation/

    **Request**

    The zip file containting your add-on should be sent as the POST data
    directly. The ``Content-Type`` header *must* to be set to
    ``application/zip`` and the ``Content-Disposition`` header *must* be set to
    ``form-data; name="binary_data"; filename="extension.zip"``

    **Response**

    Returns a :ref:`validation <addon_validation-response-label>` result.

    :status 201: successfully created, processed.
    :status 202: successfully created, still processing.

.. _addon_validation-response-label:

.. http:get:: /api/v2/extensions/validation/(string:id)/

    **Response**

    Returns a particular validation. You should poll this API until it returns
    a result with the ``processed`` property set to ``true`` before moving on
    with the submission process.

    :param id: the id of the validation.
    :type id: string
    :param processed: if the validation has been processed.
    :type processed: boolean
    :param valid: if the validation passed.
    :type valid: boolean
    :param validation: the resulting validation messages if it failed.
    :type validation: string
    :status 200: successfully completed.


.. _addon_creation:

Addon Creation
==============

.. _addon-post-label:

.. http:post:: /api/v2/extensions/extension/

    .. note:: Requires authentication and a successful validation result.

    **Request**

    :param upload: the id of the :ref:`validation result <addon_validation>`
        for your addon.
    :type upload: string

    **Response**

    :status: 201 successfully created.


To Be Continued...

