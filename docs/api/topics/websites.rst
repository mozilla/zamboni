.. _websites:

========
Websites
========

Website
=======

.. note::

    The `name`, `description`, `short_name`, and `title` fields are 
    user-translated fields and have a dynamic type depending on the query.
    See :ref:`translations <overview-translations>`.


.. _website-response-label:

.. http:get:: /api/v2/websites/website/(int:id)/

    **Response**

    A website object, see below for an example.

    :status 200: successfully completed.
    :status 404: not found.

    Example:

    .. code-block:: json

        {
          "categories": [
            "news"
          ],
          "created": "2014-11-18T14:13:12",
          "description": {
            "en-US": "Example site description"
          },
          "icons": {
            "64": "https://marketplace-dev-cdn.allizom.org/media/img/hub/default-64.png",
            "128": "https://marketplace-dev-cdn.allizom.org/media/img/hub/default-128.png",
            "48": "https://marketplace-dev-cdn.allizom.org/media/img/hub/default-48.png",
            "32": "https://marketplace-dev-cdn.allizom.org/media/img/hub/default-32.png"
          },
          "id": 42,
          "mobile_url": null,
          "name": {
            "en-US": "Example site name"
          },
          "short_name": {
            "en-US": "Example"
          },
          "title": {
            "en-US": "Example site title"
          },
          "tv_url": null,
          "url": "http://example.url/"
        }

    Fields on the response:

    :param categories: An array of strings representing the slugs of the
        categories the app belongs to.
    :type categories: array
    :param created: The date the app was added to the Marketplace, in ISO 8601
        format.
    :type created: string
    :param description: The site's description.
    :type description: string|object
    :param icons: An object containing information about the site icons. The
        keys represent icon sizes, the values the corresponding URLs.
    :type icons: object
    :param id: The site ID.
    :type id: int
    :param mobile_url: The site's mobile-specific URL, if it exists.
    :type mobile_url: string|null
    :param tv_url: The site's TV-specific URL, if it exists.
    :type tv_url: string|null
    :param name: The site's name, as used on its detail page in Marketplace.
    :type name: string|object
    :param short_name: A shorter representation of the site's name, to be used in the
        listing pages in Marketplace.
    :type short_name: string|object
    :param title: The site's title, extracted from the site's <title> element. Used
        internally to improve search results.
    :type title: string|object
    :param url: The site's URL.
    :type url: string


Website Submission
==================

.. note:: Authentication and the 'Websites:Submit' permission are required.

.. _website-submit:

.. http:post:: /api/v2/websites/website/submit/

    **Request**

    .. code-block:: json

      {
        'canonical_url': 'https://www.bro.app',
        'categories': ['lifestyle', 'music'],
        'detected_icon': 'https://www.bro.app/apple-touch.png',
        'description': 'We cannot tell you what a Bro is. But bros know.',
        'keywords': ['social networking', 'Gilfoyle', 'Silicon Valley'],
        'name': 'Bro',
        'preferred_regions': ['us', 'ca', 'fr'],
        'public_credit': False,
        'url': 'https://m.bro.app',
        'why_relevant': 'Ummm...bro. You know.',
        'works_well': 3
      }

    :param canonical_url: the canonical URL to the website, if one can be
        detected.
    :type canonical_url: string
    :param categories: slugs of categories to which the website belongs.
    :type categories: array
    :param detected_icon: the URL to an icon for the website.
    :type detected_icon: string
    :param description: a description of the website.
    :type description: string
    :param keywords: website keywords
    :type keywords: array
    :param name: the name of the website
    :type name: string
    :param preferred_regions: the regions in which the website is specifically
        relevant.
    :type preferred_regions: array
    :param public_credit: whether or not the user wants public credit for
        submitting the website.
    :type public_credit: boolean
    :param url: the url of the website
    :type url: string
    :param why_relevant: why the submitters believes the website belongs in
        Marketplace.
    :type why_relevant: string
    :param works_well: how well the website works, on a scale of 1 (poorly) to
        5 (very well).
    :type works_well: integer

    **Response**

    :status 201: successfully created.
    :status 400: submission error, see the error message in the response body
        for more detail.
    :status 403: not authorized.
