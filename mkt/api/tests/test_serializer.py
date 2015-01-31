# -*- coding: utf-8 -*-
from django.core.handlers.wsgi import WSGIRequest
from django.test import TestCase
from django.test.client import RequestFactory

import mock
from nose.tools import eq_, ok_
from rest_framework.serializers import Serializer, ValidationError

from mkt.api.serializers import PotatoCaptchaSerializer, URLSerializerMixin
from mkt.site.fixtures import fixture
from mkt.users.models import UserProfile


class TestPotatoCaptchaSerializer(TestCase):
    fixtures = fixture('user_999')

    def setUp(self):
        self.request = mock.Mock()
        self.request.META = {}
        self.request.user = mock.Mock()
        self.context = {'request': self.request}
        self.request.user.is_authenticated = lambda: False
        self.data = {'tuber': '', 'sprout': 'potato'}

    def test_success_authenticated(self):
        self.request.user = UserProfile.objects.get(id=999)
        self.request.user.is_authenticated = lambda: True
        serializer = PotatoCaptchaSerializer(data={}, context=self.context)
        eq_(serializer.is_valid(), True)

    def test_success_anonymous(self):
        data = {'tuber': '', 'sprout': 'potato'}
        serializer = PotatoCaptchaSerializer(data=data, context=self.context)
        eq_(serializer.is_valid(), True)

    def test_no_context(self):
        data = {'tuber': '', 'sprout': 'potato'}
        with self.assertRaises(ValidationError):
            PotatoCaptchaSerializer(data=data)

    def test_error_anonymous_bad_tuber(self):
        data = {'tuber': 'HAMMMMMMMMMMMMM', 'sprout': 'potato'}
        serializer = PotatoCaptchaSerializer(data=data, context=self.context)
        eq_(serializer.is_valid(), False)

    def test_error_anonymous_bad_sprout(self):
        data = {'tuber': 'HAMMMMMMMMMMMMM', 'sprout': ''}
        serializer = PotatoCaptchaSerializer(data=data, context=self.context)
        eq_(serializer.is_valid(), False)

    def test_error_anonymous_bad_tuber_and_sprout(self):
        serializer = PotatoCaptchaSerializer(data={}, context=self.context)
        eq_(serializer.is_valid(), False)


class TestURLSerializerMixin(TestCase):
    SerializerClass = type('Potato', (URLSerializerMixin, Serializer),
                           {'Meta': None})
    Struct = type('Struct', (object,), {})
    url_basename = 'potato'

    def setUp(self):
        self.SerializerClass.Meta = type('Meta', (self.Struct,),
                                         {'model': UserProfile,
                                          'url_basename': self.url_basename})
        self.request = RequestFactory().get('/')
        self.request.API_VERSION = 1
        self.serializer = self.SerializerClass(
            context={'request': self.request})
        self.obj = self.Struct()
        self.obj.pk = 42

    @mock.patch('mkt.api.serializers.reverse')
    def test_get_url(self, mock_reverse):
        self.serializer.get_url(self.obj)
        reverse_args, reverse_kwargs = mock_reverse.call_args
        ok_(mock_reverse.called)
        eq_(reverse_args[0], '%s-detail' % self.url_basename)
        eq_(type(reverse_kwargs['request']), WSGIRequest)
        eq_(reverse_kwargs['kwargs']['pk'], self.obj.pk)
