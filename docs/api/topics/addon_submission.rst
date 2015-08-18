.. _addon_submission:

=================
Add-on Submission
=================

How to submit an Add-on
=======================

.. warning::

    Add-ons in Marketplace are experimental and not yet available in production.
    This API is not ready for public consumption yet and can change at any
    moment.


Like apps, submitting an addon involves a few steps. The client must be logged
in for all these steps and the user submitting the addon must have accepted the
terms of use.

1. :ref:`Validate your addon <validation-post-label>`. The validation will
   return a validation id.
2. :ref:`Post your app <addon-post-label>` using the validation id.
   This will create an addon and populate the data with the
   contents of the manifest. It will return the current app data.
3. :ref:`Update your addon <addon-patch-label>` if necessary.
4. :ref:`Ask for a review <addon-status-patch-label>`. All addons need to be
   reviewed, this will add it to the review queue.

To Be Continued...
