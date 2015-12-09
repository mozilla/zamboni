.. _tv:

==
TV
==

TVs using Firefox OS call specialized variants of the search and detail
APIs. These are *not recommended* for consumption by other clients and can
change in conjunction with the TV client.

App
===

.. http:get:: /api/v2/tv/app/

    A copy of :ref:`the app API <app-response-label>`. The response only
    contains the specific subset of fields TVs need.

Search
======

.. http:get:: /api/v2/tv/search/

    A copy of :ref:`the app search API <search-api>`. Like the App API above, the
    response only contains the specific subset of fields Fireplace needs.


Multi Search
============

.. http:get:: /api/v2/tv/multi-search/

    A copy of :ref:`the multi-search API <multi-search-api>`. Like the App API
    above, the response only contains the specific subset of fields TVs
    need.
