.. _emails:

================
Testing emails
================

By default in a non-production enviroment the setting `REAL_EMAIL` is set to
False, which prevents emails from being sent to addresses during testing with
live data. The contents of the emails are saved in the database instead and
can be read with the Fake email admin tool at ``/admin/mail``.


Whitelist emails
--------------

In some circumstance you want to still recieve some emails, even when
`REAL_EMAIL` is False. To whitelist addresses that should get email, rather
than have it redirected to ``/admin/mail``, create a config object named
``real_email_whitelist`` in ``/admin/models/zadmin/config/`` and enter a
comma-seperated list of addresses.
