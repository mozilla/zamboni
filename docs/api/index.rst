.. _api:

=======================
Firefox Marketplace API
=======================

API documentation for the `Firefox Marketplace`_.

.. _`Firefox Marketplace`: https://marketplace.firefox.com


Related Documentation
---------------------

* `Firefox Marketplace high-level documentation <https://marketplace.readthedocs.org>`_
* `Firefox Marketplace frontend documentation <https://marketplace-frontend.readthedocs.org>`_


Quickstart
==========

Read the :ref:`overview <overview>` to understand how the API works. If
you want to view typical responses, check out these endpoints:

 * Details on an app: https://marketplace.firefox.com/api/v1/apps/app/twitter/?format=JSON
 * Search for all hosted apps about Twitter: https://marketplace.firefox.com/api/v1/apps/search/?q=twitter&app_type=hosted&format=JSON

License
=======

Except where otherwise `noted <https://www.mozilla.org/en-US/about/legal/#site>`_, content from this API is licensed under the `Creative Commons Attribution Share-Alike License v3.0 <http://creativecommons.org/licenses/by-sa/3.0/>`_ or any later version.

Questions
=========

Updates and changes are announced on the `marketplace-api-announce`_ mailing
list. We recommend that all consumers of the API subscribe.

Questions or concerns may be raised in the #marketplace channel on
irc.mozilla.org. Bugs or feature requests are filed in `Bugzilla`_. The API
code and source for these docs lives within `Marketplace Backend`_.

.. _`marketplace-api-announce`: https://mail.mozilla.org/listinfo/marketplace-api-announce
.. _`Bugzilla`: https://bugzilla.mozilla.org/buglist.cgi?list_id=6405232&resolution=---&resolution=DUPLICATE&query_format=advanced&component=API&product=Marketplace
.. _`Marketplace Backend`: https://github.com/mozilla/zamboni

Contents
========

.. toctree::
   :maxdepth: 3
   :glob:

   topics/overview
   topics/*
