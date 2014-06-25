.. _elasticsearch:

=============
Elasticsearch
=============

Elasticsearch is a search server. Documents (key-values) get stored,
configurable queries come in, Elasticsearch scores these documents, and returns
the most relevant hits.

Also check out `elasticsearch-head <http://mobz.github.io/elasticsearch-head/>`_,
a plugin with web front-end to elasticsearch that can be easier than talking to
elasticsearch over curl.

Installation
------------

For the moment our code will not work with Elasticsearch 1.0 or later. For
that reason we must install the latest version 0.90.x. We are working on
updating our code to work with 1.0+ and then you can use your favorite
package manager to install Elasticsearch. Until then, you can install by
doing the following::

    curl -O https://download.elasticsearch.org/elasticsearch/elasticsearch/elasticsearch-0.90.13.tar.gz
    tar -xvzf elasticsearch-0.90.13.tar.gz
    cd elasticsearch-0.90.13

For running Marketplace you must install the
`ICU Analysis Plugin <http://www.elasticsearch.org/guide/reference/index-modules/analysis/icu-plugin/>`_::

    ./bin/plugin -install elasticsearch/elasticsearch-analysis-icu/1.13.0

For more about the ICU plugin, see the
`ICU Github Page <https://github.com/elasticsearch/elasticsearch-analysis-icu>`_.

Settings
--------

.. literalinclude:: /../scripts/elasticsearch/elasticsearch.yml

We use a custom analyzer for indexing add-on names since they're a little
different from normal text.

To get the same results as our servers, configure Elasticsearch by copying the
:src:`scripts/elasticsearch/elasticsearch.yml` (available in the
``scripts/elasticsearch/`` folder of your install) to your system.

For example, copy it to the local directory so it's nearby when you launch
Elasticsearch::

    cp /path/to/zamboni/scripts/elasticsearch/elasticsearch.yml .

If you don't do this your results will be slightly different, but you probably
won't notice.

Launching and Setting Up
------------------------

Launch the Elasticsearch service::

    ./bin/elasticsearch -f -D elasticsearch.yml

Zamboni has commands that sets up mappings and indexes for you. Setting up
the mappings is analagous to defining the structure of a table, indexing
is analagous to storing rows.

It is worth noting that the index is maintained incrementally through
post_save and post_delete hooks.

Use this to create the apps index and index apps::

    ./manage.py reindex_mkt

Or you could use the makefile target (using the ``settings_local.py`` file)::

    make reindex

If you need to use another settings file and add arguments::

    make SETTINGS=settings_other ARGS='--with-stats --wipe --force' reindex

Querying Elasticsearch in Django
--------------------------------

We use `elasticutils <http://github.com/mozilla/elasticutils>`_, a Python
library that gives us a search API to elasticsearch.

We attach elasticutils to Django models with a mixin. This lets us do things
like ``.search()`` which returns an object which acts a lot like Django's ORM's
object manager. ``.filter(**kwargs)`` can be run on this search object::

    query_results = list(
        MyModel.search().filter(my_field=a_str.lower())
        .values_dict('that_field'))

On Marketplace, apps use ``mkt/webapps/indexers:WebappIndexer`` as its
interface to Elasticsearch. Search is done a little differently using
this and results are a list of ``WebappIndexer`` objects::

    query_results = WebappIndexer.search().filter(...)

Testing with Elasticsearch
--------------------------

All test cases using Elasticsearch should inherit from ``amo.tests.ESTestCase``.
All such tests will be skipped by the test runner unless::

    RUN_ES_TESTS = True

This is done as a performance optimization to keep the run time of the test
suite down, unless necessary.

Troubleshooting
---------------

*I got a CircularReference error on .search()* - check that a whole object is
not being passed into the filters, but rather just a field's value.

*I indexed something into Elasticsearch, but my query returns nothing* - check
whether the query contains upper-case letters or hyphens. If so, try
lowercasing your query filter. For hyphens, set the field's mapping to not be
analyzed::

    'my_field': {'type': 'string', 'index': 'not_analyzed'}

Try running .values_dict on the query as mentioned above.
