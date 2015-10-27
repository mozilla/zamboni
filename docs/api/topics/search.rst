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

    :param string doc_type (optionnal): The type of content to search for,
        separated by a comma (without spaces). Defaults to ``webapp,website`` if
        absent or invalid. Supported content types: ``webapp``, ``website`` and
        ``extension``.
    :type doc_type: string

    **Response**

    Similar to Search API but the ``objects`` field can contain:

     * :ref:`Apps <app-response-label>` if ``doc_type`` includes ``webapp``;
     * :ref:`Websites <website-response-label>` if ``doc_type`` includes ``website``;
     * :ref:`Firefox OS Add-ons <addon-detail>` if ``doc_type`` includes
       ``extension``.


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
of a feature. New features will always be added as the least significant
bit.

Feature table version 8:

==============  ===============================
  bit position   feature
==============  ===============================
             0  UDP Sockets
             1  OpenMobile ACL
             2  NFC
             3  1GB RAM Device
             4  512MB RAM Device
             5  Asm.js Precompilation
             6  Mobile ID
             7  Multiple Network Information
             8  Third-Party Keyboard Support
             9  TCP Sockets
            10  SystemXHR
            11  Alarms
            12  Notifications
            13  Pointer Lock
            14  Web Speech Recognition
            15  Web Speech Synthesis
            16  WebRTC PeerConnection
            17  WebRTC DataChannel
            18  WebRTC MediaStream
            19  Screen Capture
            20  Microphone
            21  Camera
            22  Quota Management
            23  Gamepad
            24  Full Screen
            25  WebM
            26  H.264
            27  Web Audio
            28  Audio
            29  MP3
            30  Smartphone-Sized Displays (qHD)
            31  Touch
            32  WebSMS
            33  WebFM
            34  Vibration
            35  Time/Clock
            36  Screen Orientation
            37  Simple Push
            38  Proximity
            39  Network Stats
            40  Network Information
            41  Idle
            42  Geolocation
            43  IndexedDB
            44  Device Storage
            45  Contacts
            46  Bluetooth
            47  Battery
            48  Archive
            49  Ambient Light Sensor
            50  Web Activities
            51  Web Payment
            52  Packaged Apps Install API
            53  App Management API
==============  ===============================


For example, a device with only the 'App Management API', 'Proximity',
'Ambient Light Sensor', and 'Vibration' features enabled would send this
feature profile signature::

    11002200000000.53.8

.. [1] `other` denotes a payment system other than the Firefox Marketplace
  payments. This field is not currently populated by the Marketplace Developer
  Hub.
