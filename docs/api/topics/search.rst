.. _search:

======
Search
======

This API allows search for apps by various properties.

.. _search-api:

Search
======

.. http:get:: /api/v2/apps/search/

    **Request**

    :param optional q: The query string to search for.
    :type q: string
    :param optional cat: The category slug to filter by. Use the category API
        to find the category slugs.
    :type cat: int|string
    :param optional dev: Filters by supported device. One of 'desktop',
        'android', or 'firefoxos'.
    :type dev: string
    :param optional device: Enables additional filtering by device profile
        if device is 'android'. One of 'mobile' or 'tablet'.
    :type device: string
    :param optional pro: A :ref:`feature profile <feature-profile-label>`
        describing the features to filter by.
    :type pro: string
    :param optional premium_types: Filters by whether the app is free or
        premium or has in-app purchasing. Any of 'free', 'free-inapp',
        'premium', 'premium-inapp', or 'other' [1]_.
    :type premium_types: string
    :param optional app_type: Filters by types of web apps. Any of 'hosted',
        'packaged', or 'privileged'.
    :type app_type: string
    :param optional manifest_url: Filters by manifest URL. Requires an
        exact match and should only return a single result if a match is
        found.
    :type manifest_url: string
    :param installs_allowed_from: Filters apps by the manifest
        'installs_allowed_from' field. The only supported value is '*'.
    :param optional offline: Filters by whether the app works offline or not.
        'True' to show offline-capable apps; 'False' to show apps requiring
        online support; any other value will show all apps unfiltered by
        offline support.
    :type offline: string
    :param optional languages: Filters apps by a supported language. Language
        codes should be provided in ISO 639-1 format, using a comma-separated
        list if supplying multiple languages.
    :type languages: string
    :param optional author: Filters by author. Requires a case-insensitive
        exact match of the author field.
    :type author: string
    :param optional region: Filters apps by a supported region. A region
        code should be provided in ISO 3166 format (e.g., `pl`). In API v1 (and
        only v1), if not provided, the region is automatically detected via
        requesting IP address. To disable automatic region detection, `None`
        may be passed.
    :type region: string
    :param optional guid: Filter for a specific app by Marketplace GUID.
    :type guid: string
    :param optional sort: The fields to sort by. One or more of 'created',
        'downloads', 'name', 'rating', 'reviewed', or 'trending'. Sorts by
        relevance by default. In every case except 'name', sorting is done in
        descending order.
    :type sort: string

    **Response**

    :param meta: :ref:`meta-response-label`.
    :type meta: object
    :param objects: A :ref:`listing <objects-response-label>` of
        :ref:`apps <app-response-label>`, with the following additional
        fields:
    :type objects: array


    .. code-block:: json

        {
            "absolute_url": https://marketplace.firefox.com/app/my-app/",
        }

    :status 200: successfully completed.


Multi-Search
============

.. _multi-search-api:

This API allows search for mixed content by various properties. Content types
include webapps and websites.

.. http:get:: /api/v2/multi-search/

    **Request**

    :param optional doc_type: The type of content to search for. Defaults to
        all types of content. Options include `webapp` or `website`.
    :type doc_type: string

    **Response**

    Similar to Search API but the `objects` field can contain
    :ref:`apps <app-response-label>` and
    :ref:`_websites <website-response-label>`


.. _feature-profile-label:

Feature Profile Signatures
==========================

Feature profile signatures indicate what features a device supports or
does not support, so the search results can exclude apps that require
features your device doesn't provide.

The format of a signature is FEATURES.SIZE.VERSION, where FEATURES is
a bitfield in hexadecimal, SIZE is its length in bits as a decimal
number, and VERSION is a decimal number indicating the version of the
features table.

Each bit in the features bitfield represents the presence or absence
of a feature.

Feature table version 7:

=====  ============================
  bit   feature
=====  ============================
    0   Multiple Network Information
    1   Third-Party Keyboard Support
    2   TCP Sockets
    3   SystemXHR
    4   Alarms
    5   Notifications
    6   Pointer Lock
    7   Web Speech Recognition
    8   Web Speech Synthesis
    9   WebRTC PeerConnection
   10   WebRTC DataChannel
   11   WebRTC MediaStream
   12   Screen Capture
   13   Microphone
   14   Camera
   15   Quota Management
   16   Gamepad
   17   Full Screen
   18   WebM
   19   H.264
   20   Web Audio
   21   Audio
   22   MP3
   23   Smartphone-Sized Displays
   24   Touch
   25   WebSMS
   26   WebFM
   27   Vibration
   28   Time/Clock
   29   Screen Orientation
   30   Simple Push
   31   Proximity
   32   Network Stats
   33   Network Information
   34   Idle
   35   Geolocation
   36   IndexedDB
   37   Device Storage
   38   Contacts
   39   Bluetooth
   40   Battery
   41   Archive
   42   Ambient Light Sensor
   43   Web Activities
   44   Web Payment
   45   Packaged Apps Install API
   46   App Management API
   47   Mobile ID
   48   Asm.js Precompilation
   49   512MB RAM Device
   50   1GB RAM Device
   51   NFC
=====  ============================


For example, a device with only the 'App Management API', 'Proximity',
'Ambient Light Sensor', and 'Vibration' features enabled would send this
feature profile signature::

    8801000000000.52.7

.. [1] `other` denotes a payment system other than the Firefox Marketplace
  payments. This field is not currently populated by the Marketplace Developer
  Hub.
