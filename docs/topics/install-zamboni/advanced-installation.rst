.. _advanced-installation:

=================
Optional installs
=================

All of these are optional, you can get up and running without having to setup
any of this.

--------------------
Virtual environments
--------------------

virtualenvwrapper lets you run hooks when creating, activating, and deleting
virtual environments.  These hooks can change settings, the shell environment,
or anything else you want to do from a shell script.  For complete hook
documentation, see
http://www.doughellmann.com/docs/virtualenvwrapper/hooks.html.

You can find some lovely hooks to get started at http://gist.github.com/536998.
The hook files should go in ``$WORKON_HOME`` (``$HOME/Envs`` from
above), and ``premkvirtualenv`` should be made executable.

.. _configure-mysql:

-----
MySQL
-----

On your dev machine, MySQL probably needs some tweaks. Locate your my.cnf (or
create one) then, at the very least, make UTF8 the default encoding::

    [mysqld]
    character-set-server=utf8

Here are some other helpful settings::

    [mysqld]
    default-storage-engine=innodb
    character-set-server=utf8
    skip-sync-frm=OFF
    innodb_file_per_table

On Mac OS X with homebrew, put my.cnf in ``/usr/local/Cellar/mysql/5.5.15/my.cnf`` then restart like::

    launchctl unload -w ~/Library/LaunchAgents/com.mysql.mysqld.plist
    launchctl load -w ~/Library/LaunchAgents/com.mysql.mysqld.plist

.. note:: some of the options above were renamed between MySQL versions

Here are `more tips for optimizing MySQL <http://bonesmoses.org/2011/02/28/mysql-isnt-yoursql/>`_ on your dev machine.

---------
Memcached
---------

By default zamboni uses an in memory cache. To install memcached
``libmemcached-dev`` on Ubuntu and ``libmemcached`` on OS X.  Alter your
local settings file to use::

    CACHES = {
        'default': {
            'BACKEND': 'caching.backends.memcached.MemcachedCache',
            'LOCATION': ['localhost:11211'],
            'TIMEOUT': 500,
        }
    }

-------------------
RabbitMQ and Celery
-------------------

By default zamboni automatically processes jobs without needing celery.

See the :doc:`./celery` page for installation instructions.  The
:ref:`example settings <example-settings>` set ``CELERY_ALWAYS_EAGER = True``.
If you're setting up Rabbit and want to use ``celeryd`` you will need to
alter you local settings file to set this up.

See :doc:`./celery` for more instructions.

-------------
elasticsearch
-------------

See :doc:`./elasticsearch` for more instructions.

-----
Redis
-----

On OS X the package is called ``redis``.  Get it running with the ``launchctl``
script included in homebrew.  To let zamboni know about Redis, add this to
``settings_local.py``::

    CACHE_MACHINE_USE_REDIS = True
    REDIS_BACKEND = 'redis://'

The ``REDIS_BACKEND`` is parsed like ``CACHE_BACKEND`` if you need something
other than the default settings.


-------
Node.js
-------

`Node.js <http://nodejs.org/>`_ is needed for Stylus and LESS, which in turn
are needed to precompile the CSS files.

If you want to serve the CSS files from another domain than the webserver, you
will need to precompile them. Otherwise you can have them compiled on the fly,
using javascript in your browser, if you set ``LESS_PREPROCESS = False`` in
your local settings.

First, we need to install node and npm::

    brew install node
    curl http://npmjs.org/install.sh | sh

Optionally make the local scripts available on your path if you don't already
have this in your profile::

    export PATH="./node_modules/.bin/:${PATH}"

Not working?
 * If you're having trouble installing node, try
   http://shapeshed.com/journal/setting-up-nodejs-and-npm-on-mac-osx/.  You
   need brew, which we used earlier.
 * If you're having trouble with npm, check out the README on
   https://github.com/isaacs/npm


----------
Stylus CSS
----------

Learn about Stylus at http://learnboost.github.com/stylus/ ::

    cd zamboni
    npm install

In your ``settings_local.py`` (or ``settings_local_mkt.py``) ensure you are
pointing to the correct executable for ``stylus``::

    STYLUS_BIN = path('node_modules/stylus/bin/stylus')
