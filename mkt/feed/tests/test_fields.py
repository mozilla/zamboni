# -*- coding: utf-8 -*-
from nose.tools import eq_

import amo.tests

import mkt.feed.constants as feed
from mkt.feed.fields import AppESField
from mkt.feed.tests.test_models import FeedTestMixin
from mkt.webapps.indexers import WebappIndexer


class TestAppESField(amo.tests.TestCase):

    def test_deserialize_single(self):
        app = amo.tests.app_factory(description={'en-US': 'lol'})
        app_map = {app.id: app.get_indexer().extract_document(app.id)}
        field = AppESField(source='app')
        field.context = {'app_map': app_map,
                         'request': amo.tests.req_factory_factory('')}
        data = field.to_native(app.id)

        eq_(data['id'], app.id)
        eq_(data['slug'], app.app_slug)
        eq_(data['description'], {'en-US': 'lol'})

    def test_deserialize_multi(self):
        apps = [amo.tests.app_factory(), amo.tests.app_factory()]
        app_map = dict((app.id, app.get_indexer().extract_document(app.id))
                       for app in apps)
        field = AppESField(many=True)
        field.context = {'app_map': app_map,
                         'request': amo.tests.req_factory_factory('')}
        data = field.to_native([app.id for app in apps])

        eq_(len(data), 2)
        eq_(data[0]['id'], apps[0].id)
        eq_(data[1]['id'], apps[1].id)

    def test_deserialize_limit(self):
        apps = [amo.tests.app_factory(), amo.tests.app_factory()]
        app_map = dict((app.id, app.get_indexer().extract_document(app.id))
                       for app in apps)
        field = AppESField(many=True, limit=1)
        field.context = {'app_map': app_map,
                         'request': amo.tests.req_factory_factory('')}
        data = field.to_native([app.id for app in apps])

        eq_(len(data), 1)
        eq_(data[0]['id'], apps[0].id)

        field.limit = 0
        data = field.to_native([app.id for app in apps])
        eq_(len(data), 0)
