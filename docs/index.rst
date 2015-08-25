===================================
Welcome to Zamboni's documentation!
===================================

Zamboni is one of the codebases for https://marketplace.firefox.com/

The source lives at https://github.com/mozilla/zamboni


Installation
------------
*Before* you install zamboni, we strongly recommend you start with the
`Marketplace Documentation`_ which illustrates how the Marketplace is comprised
of multiple components, one of which is zamboni.

What are you waiting for?! :ref:`Install Zamboni! <installation>`

Want to know about how development at Mozilla works, including style guides?
:ref:`Mozilla Bootcamp <http://mozweb.readthedocs.org/en/latest/index.html>`

Contents
--------

.. toctree::
   :maxdepth: 2

   topics/install-zamboni/index
   topics/hacking/index

.. toctree::
   :maxdepth: 2
   :glob:

   topics/*

How to build these docs
~~~~~~~~~~~~~~~~~~~~~~~

To simply build the docs::

    make docs

If you're working on the docs, use ``make loop`` to keep your built pages
up-to-date::

    cd docs && make loop

.. _`Marketplace Documentation`: https://marketplace.readthedocs.org
