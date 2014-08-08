# -*- coding: utf-8 -*-
from nose.tools import eq_
import os

from django.core.files.base import File
from rest_framework.exceptions import ParseError

import mock
from rest_framework import serializers

import amo.tests

import mkt.feed.constants as feed
from mkt.feed.fields import AppESField, ImageURLField
from mkt.feed.tests.test_models import FeedTestMixin
from mkt.webapps.indexers import WebappIndexer


TEST_DIR = os.path.dirname(os.path.abspath(__file__))
FILES_DIR = os.path.join(TEST_DIR, 'files')


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


class TestImageURLField(amo.tests.TestCase):

    @mock.patch('mkt.feed.fields.requests.get')
    def test_basic(self, download_mock):
        res_mock = mock.Mock()
        res_mock.status_code = 200
        res_mock.content = open(
            os.path.join(FILES_DIR, 'bacon.jpg'), 'r').read()
        download_mock.return_value = res_mock

        img, hash_ = ImageURLField().from_native('http://ngokevin.com')  # SEO.
        assert isinstance(img, File)
        assert isinstance(hash_, str)

    @mock.patch('mkt.feed.fields.requests.get')
    def test_404(self, download_mock):
        res_mock = mock.Mock()
        res_mock.status_code = 404
        res_mock.content = ''
        download_mock.return_value = res_mock

        with self.assertRaises(ParseError):
            img, hash_ = ImageURLField().from_native('http://ngokevin.com')

    def test_invalid_url(self):
        with self.assertRaises(ParseError):
            img, hash_ = ImageURLField().from_native('@#$%^&*()_')

    @mock.patch('mkt.feed.fields.requests.get')
    def test_invalid_image(self, download_mock):
        res_mock = mock.Mock()
        res_mock.status_code = 200
        res_mock.content = 'dalskdjasldkas'
        download_mock.return_value = res_mock

        with self.assertRaises(ParseError):
            img, hash_ = ImageURLField().from_native('http://ngokevin.com')
