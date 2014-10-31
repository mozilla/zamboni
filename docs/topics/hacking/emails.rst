.. _emails:

==============
Testing emails
==============

By default in a non-production enviroment the setting `REAL_EMAIL` is set to
False, which prevents emails from being sent to addresses during testing with
live data. The contents of the emails are saved in the database instead and
can be read with the Fake email admin tool at ``/admin/mail``.


Whitelist emails
----------------

In some circumstance you want to still recieve some emails, even when
`REAL_EMAIL` is False. To whitelist addresses that should get email, rather
than be redirected to ``/admin/mail``, use ``mkt.zadmin.models.set_config`` to
set the ``real_email_regex_whitelist`` key to a comma separated list of valid
emails in regex format::

    from mkt.zadmin.models import set_config
    set_config('real_email_regex_whitelist', '.+@mozilla\.com$,you@who\.ca$')
