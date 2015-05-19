.. _comm:

=============
Communication
=============

API for communication between reviewers and developers

.. note:: Under development.

App
===

.. http:get:: /api/v2/comm/app/(int:id|string:slug)/

    .. note:: Requires authentication.

    Returns all threads for the app.

    **Request**

    Takes an app slug.

    The standard :ref:`list-query-params-label`.

    **Response**

    :status 200: successfully completed.
    :status 403: not allowed to access this app.
    :status 404: app not found.

    :param meta: :ref:`meta-response-label`.
    :type meta: object
    :param objects: A :ref:`listing <objects-response-label>` of
        :ref:`threads <thread-response-label>`.
    :type objects: array

    **?serializer=simple**

    If you pass *simple* as a value to the *serializer* GET parameter, the
    deserialized threads will consist only of the thread ID and the version
    number for the app it is representing.

    Example:

    .. code-block:: json

        {
            "objects": [
                {
                    "id": 12345,
                    "version": {
                        "id": 444,
                        "version": "1.2"
                    }
                },
                {
                    "id": 12348,
                    "version": {
                        "id": 474,
                        "version": "1.3"
                    }
                }
            ],
        }


Thread
======

.. http:get:: /api/v2/comm/thread/

    .. note:: Requires authentication.

    Returns a list of threads in which the user is involved in.

    **Request**

    The standard :ref:`list-query-params-label`.

    **Response**

    :param meta: :ref:`meta-response-label`.
    :type meta: object
    :param objects: A :ref:`listing <objects-response-label>` of
         :ref:`threads <thread-response-label>`.
    :type objects: array


.. _thread-response-label:

.. http:get:: /api/v2/comm/thread/(int:id)/

    .. note:: Requires authentication.

    View a thread object.

    **Response**

    A thread object, see below for example.

    :status 200: successfully completed.
    :status 403: not allowed to access this object.
    :status 404: not found.

    Example:

    .. code-block:: json

        {
            "app": {
                "app_slug": "app-3",
                "id": 5,
                "name": "Test App (kinkajou3969)",
                "review_url": "/reviewers/apps/review/test-app-kinkajou3969/",
                "thumbnail_url": "/tmp/uploads/previews/thumbs/0/37.png?modified=1362762723",
                "url": "/app/test-app-kinkajou3969/"
            },
            "created": "2013-06-14T11:54:24",
            "id": 2,
            "modified": "2013-06-24T22:01:37",
            "notes_count": 47,
            "version": {
                "id": 45,
                "version": "1.6",
                "deleted": false
            }
        }

    Notes on the response.

    :param version.version: Version number noted from the app manifest.
    :type version.version: string
    :param version.deleted: whether the version of the app of the note is
        out-of-date.
    :type version.deleted: boolean


.. http:post:: /api/v2/comm/thread/

    .. note:: Requires authentication.

    Create a thread from a new note for a version of an app.

    **Request**

    :param app: id or slug of the app to filter the threads by.
    :type app: int|string
    :param version: version number for the thread's :ref:`version <versions-label>` (e.g. 1.2).
    :type version: string
    :param note_type: a :ref:`note type label <note-type-label>`.
    :type note_type: int
    :param body: contents of the note.
    :type body: string

    **Response**

    A :ref:`note <note-response-label>` object.


Note
====

.. http:get:: /api/v2/comm/thread/(int:thread_id)/note/

    .. note:: Requires authentication.

    Returns the list of notes that a thread contains.

    **Request**

    The standard :ref:`list-query-params-label`.

    For ordering params, see :ref:`list-ordering-params-label`.

    In addition to above, there is another query param:

    :param show_read: Filter notes by read status. Pass `true` to list read notes and `false` for unread notes.
    :type show_read: boolean

    **Response**

    :param meta: :ref:`meta-response-label`.
    :param objects: A :ref:`listing <objects-response-label>` of :ref:`notes <note-response-label>`.

.. _note-response-label:

.. http:get:: /api/v2/comm/thread/(int:thread_id)/note/(int:id)/

    .. note:: Requires authentication.

    View a note.

    **Request**

    The standard :ref:`list-query-params-label`.

    **Response**

    A note object, see below for example.

    :status 200: successfully completed.
    :status 403: not allowed to access this object.
    :status 404: thread or note not found.

    .. code-block:: json

        {
            "attachments": [{
                "id": 1,
                "created": "2013-06-14T11:54:48",
                "display_name": "Screenshot of my app.",
                "url": "http://marketplace.cdn.mozilla.net/someImage.jpg",
            }],
            "author": 1,
            "author_meta": {
                "name": "Admin"
            },
            "body": "hi there",
            "created": "2013-06-14T11:54:48",
            "id": 2,
            "note_type": 0,
            "thread": 2,
        }

    Notes on the response.

    :param attachments: files attached to the note (often images).
    :type attachments: array
    :param note_type: type of action taken with the note.
    :type note_type: int

.. _note-type-label:

    Only "No Action", "Reviewer Comment", and "Developer Comment" note types
    can be created through the Note API. Further, one must be a reviewer to
    make a "Reviewer Comment". And one must be a developer of an app to make
    a "Developer Comment" on an app's thread.

    All note types are listed in the `code <https://github.com/mozilla/zamboni/blob/master/mkt/constants/comm.py>`_


.. _note-post-label:

.. http:post:: /api/v2/comm/thread/(int:thread_id)/note/

    .. note:: Requires authentication.

    Create a note on a thread.

    **Request**

    :param author: the id of the author.
    :type author: int
    :param thread: the id of the thread to post to.
    :type thread: int
    :param note_type: the type of note to create. See :ref:`supported types <note-type-label>`.
    :type note_type: int
    :param body: the comment text to be attached with the note.
    :type body: string

    **Response**

    :param: A :ref:`note <note-response-label>`.
    :status: 201 successfully created.
    :status: 400 bad request.
    :status: 404 thread not found.


.. _list-ordering-params-label:

List ordering params
~~~~~~~~~~~~~~~~~~~~

Order results by created or modified times, by using `ordering` param.

* *created* - Earliest created notes first.

* *-created* - Latest created notes first.

* *modified* - Earliest modified notes first.

* *-modified* - Latest modified notes first.


Attachment
==========

.. _attachment-post-label:

.. http:post:: /api/v2/comm/note/(int:note_id)/attachment

    .. note:: Requires authentication and the user to be the author of the note.

    Create attachment(s) on a note.

    **Request**

    The request must be sent and encoded with the multipart/form-data Content-Type.

    :param form-0-attachment: the first attachment file encoded with multipart/form-data.
    :type form-0-attachment: multipart/form-data encoded file stream
    :param form-0-description: description of the first attachment.
    :type form-0-description: string
    :param form-N-attachment: If sending multiple attachments, replace N with the number of the n-th attachment.
    :type form-N-attachment: multipart/form-data encoded file stream
    :param form-N-description: description of the n-th attachment.
    :type form-N-description: string

    **Response**

    :param: The :ref:`note <note-response-label>` the attachment was attached to.
    :status: 201 successfully created.
    :status: 400 bad request (e.g. no attachments, more than 10 attachments).
    :status: 403 permission denied if user isn't the author of the note.
