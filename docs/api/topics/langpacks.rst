.. _langpacks:
.. versionadded:: 2

=========
Langpacks
=========

Currently in development, subject to change. Follow https://bugzilla.mozilla.org/show_bug.cgi?id=1105530
for more information.

List
====

.. http:get:: /api/v2/langpacks/

    Returns a list of active langpacks.

    **Request**

    The standard :ref:`list-query-params-label`.

    If the request is authenticated and the user has the ``LangPacks:%``
    permission, then the following additional parameters are accepted:

    :param active: a flag indicating whether the response should include inactive langpacks or not. Pass `active=null` to show all langpacks regardless of their active status, and pass `active=false` to only show inactive langpacks.
    :type active: string

    **Response**

    :param meta: :ref:`meta-response-label`.
    :type meta: object
    :param objects: A :ref:`listing <objects-response-label>` of :ref:`langpacks <langpack-response-label>`.
    :type objects: array

Detail
======

.. _langpack-response-label:
.. http:get:: /api/v2/langpacks/(string:uuid)/

    Returns a single langpack. If the request is authenticated and the user has the ``LangPacks:%`` permission, inactive langpacks
    can be returned.

    **Response**

    :param active: A boolean representing the langpack state. Inactive langpacks are hidden by default.
    :type active: boolean
    :param created: The date that the langpack was first uploaded (in ISO 8601 format).
    :type created: string
    :param fxos_version: The Firefox OS version this langpack provides translations for.
    :type fxos_version: string
    :param language: The language code (i.e. "de", or "pt-BR") this langpack provides translations for.
    :type language: string
    :param language_display: The language this langpack provides translations for, in a human-readable format (i.e. Deutsch).
    :type language_display: string
    :param manifest_url: The URL to the mini-manifest for this package, which contains everything needed to install and update the language pack.
    :type active: string
    :param modified: The date that the langpack was last modified (in ISO 8601 format).
    :type modified: string
    :param uuid: Unique identifier for this langpack.
    :type uuid: string
    :param version: The version of the Langpack package itself.
    :type version: string

Langpack properties edition
===========================

.. _langpack-patch:
.. http:patch:: /api/v2/langpacks/(string:uuid)/

    .. note:: Requires authentication and the ``LangPacks:%`` permission.

    :param active: A boolean representing the langpack state. Inactive langpacks are hidden by default.
    :type active: boolean

Deletion
==============

.. http:delete:: /api/v2/langpacks/(string:uuid)/

    .. note:: Requires authentication and the ``LangPacks:%`` permission.

Creation
========

To upload a new langpack, the process is similar to app submission. First you
need to upload your package to the :ref:`validation endpoint <validation-post-label>`,
and then, once the package has been validated, you can use the validation id in the
endpoints below:

.. http:post:: /api/v2/langpacks/

    .. note:: Requires authentication and the ``LangPacks:%`` permission.
    .. note:: By default, langpacks are created inactive. Once everything looks ok, use :ref:`the patch API <langpack-patch>` to activate a langpack.

    :param required upload: Validation id.
    :type upload: string

Package update
==============

.. http:put:: /api/v2/langpacks/(string:uuid)/

    .. note:: Requires authentication and the ``LangPacks:%`` permission.

    :param required upload: Validation id.
    :type upload: string
