import json
import os
from urlparse import urljoin
from uuid import UUID, uuid4

import mock
from django.conf import settings
from django.test import TestCase
from nose.tools import eq_, ok_

from lib.iarc_v2.client import (get_rating_changes, publish, unpublish,
                                search_and_attach_cert)
from mkt.constants.ratingsbodies import CLASSIND_12, ESRB_10
from mkt.site.utils import app_factory
from mkt.webapps.models import IARCCert, RatingDescriptors, Webapp


mock_root = os.path.join(settings.ROOT, 'lib', 'iarc_v2', 'mock')


def _get_mock_response(service_name):
    class Response(object):
        def json(self):
            with open(os.path.join(mock_root, '%s.json' % service_name)) as f:
                data = f.read()
            return json.loads(data)
    return Response()


class TestGetRatingChanges(TestCase):

    @mock.patch('lib.iarc_v2.client.requests.get')
    def test_no_existing_certs_does_not_raise_an_error(self, req_mock):
        req_mock.return_value = _get_mock_response('GetRatingChanges')
        res = get_rating_changes()
        eq_(res['Result']['ResponseCode'], 'Success')

    @mock.patch('lib.iarc_v2.client.requests.get')
    def test_with_existing_cert_valid(self, req_mock):
        req_mock.return_value = _get_mock_response('GetRatingChanges')
        data = req_mock.return_value.json()
        cert_id_1 = data['CertList'][0]['CertID']
        cert_id_2 = data['CertList'][1]['CertID']
        app1 = app_factory()
        app2 = app_factory()
        IARCCert.objects.create(app=app1, cert_id=UUID(cert_id_1))
        IARCCert.objects.create(app=app2, cert_id=UUID(cert_id_2))
        eq_(RatingDescriptors.objects.filter(addon=app1).count(), 0)
        RatingDescriptors.objects.create(addon=app2, has_esrb_lang=True)
        eq_(app2.rating_descriptors.to_keys(), ['has_esrb_lang'])

        res = get_rating_changes()
        eq_(UUID(app1.iarc_cert.cert_id), UUID(cert_id_1))
        eq_(UUID(app2.iarc_cert.cert_id), UUID(cert_id_2))

        # Compare with mock data. Force reload using .objects.get in order to
        # properly reset the related objects caching.
        app1 = Webapp.objects.get(pk=app1.pk)
        app2 = Webapp.objects.get(pk=app2.pk)
        eq_(app1.rating_descriptors.to_keys(), ['has_esrb_violence_ref'])
        eq_(app2.rating_descriptors.to_keys(),
            ['has_classind_violence', 'has_esrb_violence', 'has_usk_violence'])
        eq_(res['Result']['ResponseCode'], 'Success')
        eq_(app1.content_ratings.all()[0].get_rating_class(), ESRB_10)
        eq_(app2.content_ratings.all()[0].get_rating_class(), CLASSIND_12)


class TestUpdateCerts(TestCase):

    @mock.patch('lib.iarc_v2.client.requests.post')
    def test_publish(self, req_mock):
        req_mock.return_value = _get_mock_response('UpdateCerts')
        app = mock.Mock()
        app.iarc_cert.cert_id = 'adb3261bc6574fd2a057bc9f85310b80'
        res = publish(app)
        eq_(res['ResultList'][0]['ResultCode'], 'Success')
        eq_(req_mock.call_count, 1)
        eq_(req_mock.call_args[0][0],
            urljoin(settings.IARC_V2_SERVICE_ENDPOINT, 'UpdateCerts'))
        eq_(req_mock.call_args[1], {
            'data': {
                'UpdateList': [{
                    'Action': 'Publish',
                    'CertID': 'adb3261b-c657-4fd2-a057-bc9f85310b80'
                }]
            }
        })

    @mock.patch('lib.iarc_v2.client.requests.post')
    def test_publish_no_cert(self, req_mock):
        app = Webapp()
        res = publish(app)
        eq_(res, None)
        eq_(req_mock.call_count, 0)

    @mock.patch('lib.iarc_v2.client.requests.post')
    def test_unpublish(self, req_mock):
        req_mock.return_value = _get_mock_response('UpdateCerts')
        app = mock.Mock()
        app.iarc_cert.cert_id = 'adb3261bc6574fd2a057bc9f85310b80'
        res = unpublish(app)
        eq_(res['ResultList'][0]['ResultCode'], 'Success')
        eq_(req_mock.call_count, 1)
        eq_(req_mock.call_args[0][0],
            urljoin(settings.IARC_V2_SERVICE_ENDPOINT, 'UpdateCerts'))
        eq_(req_mock.call_args[1], {
            'data': {
                'UpdateList': [{
                    'Action': 'RemoveProduct',
                    'CertID': 'adb3261b-c657-4fd2-a057-bc9f85310b80'
                }]
            }
        })

    @mock.patch('lib.iarc_v2.client.requests.post')
    def test_unpublish_no_cert(self, req_mock):
        app = Webapp()
        res = unpublish(app)
        eq_(res, None)
        eq_(req_mock.call_count, 0)


class TestSearchCerts(TestCase):

    @mock.patch('lib.iarc_v2.client.requests.get')
    def test_uuid_hex_string_with_separators(self, req_mock):
        req_mock.return_value = _get_mock_response('SearchCerts')
        res = search_and_attach_cert(mock.Mock(), unicode(uuid4()))
        ok_(res['MatchFound'])

    @mock.patch('lib.iarc_v2.client.requests.get')
    def test_uuid_hex_string(self, req_mock):
        req_mock.return_value = _get_mock_response('SearchCerts')
        res = search_and_attach_cert(mock.Mock(), uuid4().get_hex())
        ok_(res['MatchFound'])
