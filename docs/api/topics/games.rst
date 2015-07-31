.. _games:

=====
Games
=====

This API allows search for featured games.

.. _games-api:

Daily Games
===========

.. http:get:: /api/v2/games/daily/

    Returns a small set of featured games, one game from each featured game
    category (e.g., action, adventure, puzzle, strategy). This set will be
    randomly updated daily.

    **Response**

    :param meta: :ref:`meta-response-label`.
    :type meta: object
    :param objects: A :ref:`listing <objects-response-label>` of
        :ref:`apps <app-response-label>` and
        :ref:`websites <website-response-label>` that are tagged as featured
        games.
    :type objects: array
    :status 200: successfully completed.

Featured Game Listings
======================

.. http:get:: /api/v2/apps/search/?tag=featured-game

    **Response**

    Returns apps and websites tagged as featured games.

.. http:get:: /api/v2/apps/search/?tag=featured-game-[adventure, action, puzzle, strategy]

    **Response**

    Returns apps and websites tagged as featured games, further categorized.
