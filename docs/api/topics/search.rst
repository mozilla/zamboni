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
             0  OpenMobile ACL
             1  NFC
             2  1GB RAM Device
             3  512MB RAM Device
             4  Asm.js Precompilation
             5  Mobile ID
             6  Multiple Network Information
             7  Third-Party Keyboard Support
             8  TCP Sockets
             9  SystemXHR
            10  Alarms
            11  Notifications
            12  Pointer Lock
            13  Web Speech Recognition
            14  Web Speech Synthesis
            15  WebRTC PeerConnection
            16  WebRTC DataChannel
            17  WebRTC MediaStream
            18  Screen Capture
            19  Microphone
            20  Camera
            21  Quota Management
            22  Gamepad
            23  Full Screen
            24  WebM
            25  H.264
            26  Web Audio
            27  Audio
            28  MP3
            29  Smartphone-Sized Displays (qHD)
            30  Touch
            31  WebSMS
            32  WebFM
            33  Vibration
            34  Time/Clock
            35  Screen Orientation
            36  Simple Push
            37  Proximity
            38  Network Stats
            39  Network Information
            40  Idle
            41  Geolocation
            42  IndexedDB
            43  Device Storage
            44  Contacts
            45  Bluetooth
            46  Battery
            47  Archive
            48  Ambient Light Sensor
            49  Web Activities
            50  Web Payment
            51  Packaged Apps Install API
            52  App Management API
==============  ===============================


For example, a device with only the 'App Management API', 'Proximity',
'Ambient Light Sensor', and 'Vibration' features enabled would send this
feature profile signature::

    11002200000000.53.8

.. [1] `other` denotes a payment system other than the Firefox Marketplace
  payments. This field is not currently populated by the Marketplace Developer
  Hub.
