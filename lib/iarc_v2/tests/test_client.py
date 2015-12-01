import json
import os

import mock
from django.conf import settings
from django.test import TestCase
from nose.tools import eq_, ok_

from lib.iarc_v2.client import get_rating_changes, search_certs, _update_certs


mock_root = os.path.join(settings.ROOT, 'lib', 'iarc_v2', 'mock')

responses = {
    'GetRatingChanges': file(
        os.path.join(mock_root, 'GetRatingChanges.json')
    ).read(),
    'SearchCerts': file(
        os.path.join(mock_root, 'SearchCerts.json')
    ).read(),
    'UpdateCerts': file(
        os.path.join(mock_root, 'UpdateCerts.json')
    ).read()
}


def _get_response(service):
    class Response(object):
        def json(self):
            return json.loads(responses[service])
    return Response()


class TestGetRatingChanges(TestCase):

    @mock.patch('lib.iarc_v2.client.requests.get')
    def test_basic(self, req_mock):
        req_mock.return_value = _get_response('GetRatingChanges')
        res = get_rating_changes()
        eq_(res['Result']['ResponseCode'], 'Success')


class TestSearchCerts(TestCase):

    @mock.patch('lib.iarc_v2.client.requests.get')
    def test_basic(self, req_mock):
        req_mock.return_value = _get_response('SearchCerts')
        res = search_certs('abc')
        ok_(res['MatchFound'])


class TestUpdateCerts(TestCase):

    @mock.patch('lib.iarc_v2.client.requests.post')
    def test_basic(self, req_mock):
        req_mock.return_value = _get_response('UpdateCerts')
        res = _update_certs('abc', 'action')
        eq_(res['ResultList'][0]['ResultCode'], 'Success')
