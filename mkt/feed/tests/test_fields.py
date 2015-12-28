# -*- coding: utf-8 -*-
import os

from nose.tools import eq_, ok_

import mkt.site.tests
from mkt.feed.fields import AppESField


TEST_DIR = os.path.dirname(os.path.abspath(__file__))
FILES_DIR = os.path.join(TEST_DIR, 'files')


class TestAppESField(mkt.site.tests.ESTestCase):

    def test_deserialize_single(self):
        app = mkt.site.tests.app_factory(description={'en-US': 'lol'})
        app_map = {app.id: app.get_indexer().extract_document(app.id)}
        field = AppESField(source='app')
        field.context = {'app_map': app_map,
                         'request': mkt.site.tests.req_factory_factory('')}
        data = field.to_representation(app.id)

        eq_(data['id'], app.id)
        eq_(data['slug'], app.app_slug)
        eq_(data['description'], {'en-US': 'lol'})

    def test_deserialize_multi(self):
        apps = [mkt.site.tests.app_factory(), mkt.site.tests.app_factory()]
        app_map = dict((app.id, app.get_indexer().extract_document(app.id))
                       for app in apps)
        field = AppESField(many=True)
        field.context = {'app_map': app_map,
                         'request': mkt.site.tests.req_factory_factory('')}
        data = field.to_representation([app.id for app in apps])

        eq_(len(data), 2)
        eq_(data[0]['id'], apps[0].id)
        eq_(data[1]['id'], apps[1].id)

    def test_deserialize_limit(self):
        apps = [mkt.site.tests.app_factory(), mkt.site.tests.app_factory()]
        app_map = dict((app.id, app.get_indexer().extract_document(app.id))
                       for app in apps)
        field = AppESField(many=True, limit=1)
        field.context = {'app_map': app_map,
                         'request': mkt.site.tests.req_factory_factory('')}
        data = field.to_representation([app.id for app in apps])

        eq_(len(data), 1)
        eq_(data[0]['id'], apps[0].id)

        field.limit = 0
        data = field.to_representation([app.id for app in apps])
        eq_(len(data), 0)

    def test_no_exist(self):
        """
        Handle when the app is not in the app map (as result of filtering).
        """
        app = mkt.site.tests.app_factory()

        field = AppESField()
        field.context = {'app_map': {},
                         'request': mkt.site.tests.req_factory_factory('')}
        data = field.to_representation(app.id)
        ok_(not data)

    def test_multi_no_exist(self):
        """
        Handle when the app is not in the app map (as result of filtering).
        """
        apps = [mkt.site.tests.app_factory(), mkt.site.tests.app_factory()]
        app_map = {
            apps[0].id: apps[0].get_indexer().extract_document(apps[0].id)
        }

        field = AppESField(many=True)
        field.context = {'app_map': app_map,
                         'request': mkt.site.tests.req_factory_factory('')}
        data = field.to_representation([app.id for app in apps])

        eq_(len(data), 1)
        eq_(data[0]['id'], apps[0].id)
