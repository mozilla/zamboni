
=============================================
Trouble-shooting the development installation
=============================================

M2Crypto installation
---------------------

If you are on a Linux box and get a compilation error while installing M2Crypto
like the following::

    SWIG/_m2crypto_wrap.c:6116:1: error: unknown type name ‘STACK’

    ... snip a very long output of errors around STACK...

    SWIG/_m2crypto_wrap.c:23497:20: error: expected expression before ‘)’ token

       result = (STACK *)pkcs7_get0_signers(arg1,arg2,arg3);

                        ^

    error: command 'gcc' failed with exit status 1

It may be because of a `few reasons`_:

.. _few reasons:
    http://blog.rectalogic.com/2013/11/installing-m2crypto-in-python.html

* comment the line starting with ``M2Crypto`` in ``requirements/compiled.txt``
* install the patched package from the Debian repositories (replace
  ``x86_64-linux-gnu`` by ``i386-linux-gnu`` if you're on a 32bits platform)::

    DEB_HOST_MULTIARCH=x86_64-linux-gnu pip install -I --exists-action=w "git+git://anonscm.debian.org/collab-maint/m2crypto.git@debian/0.21.1-3#egg=M2Crypto"
    pip install --no-deps -r requirements/dev.txt

* revert your changes to ``requirements/compiled.txt``::

    git checkout requirements/compiled.txt

Pillow
------

As of Mac OS X Mavericks, you might see this error when pip builds Pillow::

    clang: error: unknown argument: '-mno-fused-madd' [-Wunused-command-line-argument-hard-error-in-future]

    clang: note: this will be a hard error (cannot be downgraded to a warning) in the future

    error: command 'cc' failed with exit status 1

You can solve this by setting these environment variables in your shell
before running ``pip install ...``::

    export CFLAGS=-Qunused-arguments
    export CPPFLAGS=-Qunused-arguments
    pip install ...

More info: http://stackoverflow.com/questions/22334776/installing-pillow-pil-on-mavericks/22365032

Image processing isn't working
------------------------------

If adding images to apps or extensions doesn't seem to work then there's a
couple of settings you should check.

Checking your PIL installation (Ubuntu)
_______________________________________

When you run you should see at least JPEG and ZLIB are supported

If that's the case you should see this in the output of ``pip install -I PIL``::

    --------------------------------------------------------------------
    *** TKINTER support not available
    --- JPEG support available
    --- ZLIB (PNG/ZIP) support available
    *** FREETYPE2 support not available
    *** LITTLECMS support not available
    --------------------------------------------------------------------

If you don't then this suggests PIL can't find your image libraries:

To fix this double-check you have the necessary development libraries
installed first (e.g: ``sudo apt-get install libjpeg-dev zlib1g-dev``)

Now run the following for 32bit::

    sudo ln -s /usr/lib/i386-linux-gnu/libz.so /usr/lib
    sudo ln -s /usr/lib/i386-linux-gnu/libjpeg.so /usr/lib

Or this if your running 64bit::

    sudo ln -s /usr/lib/x86_64-linux-gnu/libz.so /usr/lib
    sudo ln -s /usr/lib/x86_64-linux-gnu/libjpeg.so /usr/lib

.. note::

    If you don't know what arch you are running run ``uname -m`` if the
    output is ``x86_64`` then it's 64-bit, otherwise it's 32bit
    e.g. ``i686``


Now re-install PIL::

    pip install -I PIL

And you should see the necessary image libraries are now working with
PIL correctly.


ES is timing out
----------------

This can be caused by ``number_of_replicas`` not being set to 0 for the local indexes.

To check the settings run::

    curl -s localhost:9200/_cluster/state\?pretty | fgrep number_of_replicas -B 5

If you see any that aren't 0  do the following:

Set ``ES_DEFAULT_NUM_REPLICAS`` to ``0`` in your local settings.

To set them to zero immediately run::

    curl -XPUT localhost:9200/_settings -d '{ "index" : { "number_of_replicas" : 0 } }'
