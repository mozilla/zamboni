.. _testing:

=======
Testing
=======

We're using a mix of `Django's Unit Testing`_ and :mod:`nose <nose>`.

Running Tests
-------------

To run the whole shebang use::

    python manage.py test

There are a lot of options you can pass to adjust the output.  Read `the docs`_
for the full set, but some common ones are:

* ``-P`` to prevent nose adding the `lib` directory to the path.
* ``--noinput`` tells Django not to ask about creating or destroying test
  databases.
* ``--logging-clear-handlers`` tells nose that you don't want to see any
  logging output.  Without this, our debug logging will spew all over your
  console during test runs.  This can be useful for debugging, but it's not that
  great most of the time.  See the docs for more stuff you can do with
  :mod:`nose and logging <nose.plugins.logcapture>`.

Our continuous integration server adds some additional flags for other features
(for example, coverage statistics).  To see what those commands are check out
the :src:`.travis.yml` file.

There are a few useful makefile targets that you can use:

Run all the tests::

    make test

If you need to rebuild the database::

    make test_force_db

To fail and stop running tests on the first failure::

    make tdd

If you wish to add arguments, or run a specific test, overload the variables
(check the Makefile for more information)::

    make SETTINGS=settings_mkt ARGS='--verbosity 2 zamboni.mkt.site.tests.test_url_prefix:MiddlewareTest.test_get_app' test

Those targets include some useful options, like the ``--with-id`` which allows
you to re-run only the tests failed from the previous run::

    make test_failed


Database Setup
~~~~~~~~~~~~~~

If you want to re-use your database instead of making a new one every time you
run tests, set the environment variable ``REUSE_DB``. ::

    REUSE_DB=1 python manage.py test


Writing Tests
-------------
We support two types of automated tests right now and there are some details
below but remember, if you're confused look at existing tests for examples.


Unit/Functional Tests
~~~~~~~~~~~~~~~~~~~~~
Most tests are in this category.  Our test classes extend
:class:`django.test.TestCase` and follow the standard rules for unit tests.
We're using JSON fixtures for the data.

External calls
~~~~~~~~~~~~~~
Connecting to remote services in tests is not recommended, developers should
mock_ out those calls instead.

To enforce this we run Jenkins with the `nose-blockage`_ plugin, that
will raise errors if you have an HTTP calls in your tests apart from calls to
the domains `127.0.0.1` and `localhost`.

Why Tests Fail
--------------
Tests usually fail for one of two reasons: The code has changed or the data has
changed.  An third reason is **time**.  Some tests have time-dependent data
usually in the fixtues.  For example, some featured items have expiration dates.

We can usually save our future-selves time by setting these expirations far in
the future.


Localization Tests
------------------
If you want test that your localization works then you can add in locales
in the test directory. For an example see ``devhub/tests/locale``. These locales
are not in the normal path so should not show up unless you add them to the
`LOCALE_PATH`. If you change the .po files for these test locales, you will
need to recompile the .mo files manually, for example::

    msgfmt --check-format -o django.mo django.po


.. _`Django's Unit Testing`: http://docs.djangoproject.com/en/dev/topics/testing
.. _`Selenium repository`: https://github.com/mozilla/Addon-Tests/
.. _`the docs`: http://docs.djangoproject.com/en/dev/topics/testing#id1
.. _`nose-blockage`: https://github.com/andymckay/nose-blockage
