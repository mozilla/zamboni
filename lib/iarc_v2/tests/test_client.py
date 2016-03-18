import datetime
import json
import os
from urlparse import urljoin
from uuid import UUID, uuid4

import mock
import responses
from django.conf import settings
from django.test import TransactionTestCase
from nose.tools import eq_

from lib.iarc_v2.client import (_attach_to_cert, get_rating_changes,
                                _iarc_app_data, IARCException, publish,
                                refresh, unpublish, search_cert,
                                search_and_attach_cert)
from mkt.constants.ratingsbodies import CLASSIND_12, ESRB_10
from mkt.site.helpers import absolutify
from mkt.site.tests import app_factory, TestCase, user_factory
from mkt.webapps.models import (IARCCert, RatingDescriptors,
                                RatingInteractives, Webapp)


mock_root = os.path.join(settings.ROOT, 'lib', 'iarc_v2', 'mock')


def setup_mock_response(endpoint, data=None, status=200):
    if data is None:
        with open(os.path.join(mock_root, '%s.json' % endpoint)) as f:
            data = f.read()
    url = urljoin(settings.IARC_V2_SERVICE_ENDPOINT, endpoint)
    responses.add(responses.POST, url, data, status=status)
    try:
        # Purely for convenience, return data the caller used, as dict.
        result = json.loads(data)
    except ValueError:
        result = data
    return result


class TestGetRatingChanges(TestCase):

    @responses.activate
    def test_no_existing_certs_doesnt_raise_an_error(self):
        setup_mock_response('GetRatingChanges')
        res = get_rating_changes()
        eq_(res['Result']['ResponseCode'], 'Success')

    @responses.activate
    def test_with_date(self):
        setup_mock_response('GetRatingChanges')
        expected_end_date = (datetime.datetime.utcnow() -
                             datetime.timedelta(days=2))
        expected_start_date = expected_end_date - datetime.timedelta(days=1)
        get_rating_changes(date=expected_end_date)
        eq_(len(responses.calls), 1)
        eq_(responses.calls[0].request.headers.get('StorePassword'),
            settings.IARC_V2_STORE_PASSWORD)
        eq_(responses.calls[0].request.headers.get('StoreID'),
            settings.IARC_V2_STORE_ID)
        eq_(json.loads(responses.calls[0].request.body), {
            'StartDate': expected_start_date.strftime('%Y-%m-%d'),
            'EndDate': expected_end_date.strftime('%Y-%m-%d'),
            'MaxRows': 500,
            'StartRowIndex': 0
        })

    @responses.activate
    def test_with_existing_cert_valid(self):
        # Set up. app1 has no rating descriptors, app2 has one.
        data = setup_mock_response('GetRatingChanges')
        cert_id_1 = data['CertList'][0]['CertID']
        cert_id_2 = data['CertList'][1]['CertID']
        app1 = app_factory()
        app2 = app_factory()
        IARCCert.objects.create(app=app1, cert_id=UUID(cert_id_1))
        IARCCert.objects.create(app=app2, cert_id=UUID(cert_id_2))
        eq_(RatingDescriptors.objects.filter(addon=app1).count(), 0)
        RatingDescriptors.objects.create(addon=app2, has_esrb_lang=True)
        eq_(app2.rating_descriptors.to_keys(), ['has_esrb_lang'])
        expected_end_date = datetime.datetime.utcnow()
        expected_start_date = expected_end_date - datetime.timedelta(days=1)

        # GetRatingChanges Call.
        res = get_rating_changes()

        # Check that we called IARC as expected.
        eq_(len(responses.calls), 1)
        eq_(responses.calls[0].request.headers.get('StorePassword'),
            settings.IARC_V2_STORE_PASSWORD)
        eq_(responses.calls[0].request.headers.get('StoreID'),
            settings.IARC_V2_STORE_ID)
        eq_(json.loads(responses.calls[0].request.body), {
            'StartDate': expected_start_date.strftime('%Y-%m-%d'),
            'EndDate': expected_end_date.strftime('%Y-%m-%d'),
            'MaxRows': 500,
            'StartRowIndex': 0
        })
        eq_(res['Result']['ResponseCode'], 'Success')

        # Check that Cert IDs are still correct.
        eq_(UUID(app1.iarc_cert.cert_id), UUID(cert_id_1))
        eq_(UUID(app2.iarc_cert.cert_id), UUID(cert_id_2))

        # Compare with mock data. Force reload using .objects.get in order to
        # properly reset the related objects caching. App1 should have gained
        # a descriptor, and app2 should have lost its original descriptor and
        # gained a few.
        app1 = Webapp.objects.get(pk=app1.pk)
        app2 = Webapp.objects.get(pk=app2.pk)
        eq_(app1.rating_descriptors.to_keys(), ['has_esrb_violence_ref'])
        self.assertSetEqual(
            app2.rating_descriptors.to_keys(),
            ['has_classind_violence', 'has_generic_moderate_violence',
             'has_pegi_moderate_violence', 'has_esrb_violence',
             'has_usk_violence'])
        eq_(app1.content_ratings.all()[0].get_rating_class(), ESRB_10)
        eq_(app2.content_ratings.all()[0].get_rating_class(), CLASSIND_12)

    @responses.activate
    def test_with_existing_descriptors_that_should_be_kept(self):
        data = setup_mock_response('GetRatingChanges')
        cert_id = data['CertList'][0]['CertID']
        app = app_factory()
        IARCCert.objects.create(app=app, cert_id=UUID(cert_id))
        RatingDescriptors.objects.create(addon=app, has_classind_violence=True)

        get_rating_changes()

        eq_(UUID(app.iarc_cert.cert_id), UUID(cert_id))
        app = Webapp.objects.get(pk=app.pk)
        # Original descriptor belongs to a rating body that wasn't part of the
        # changes returned by GetRatingChanges for this cert, so it should have
        # been kept.
        self.assertSetEqual(app.rating_descriptors.to_keys(),
                            ['has_classind_violence', 'has_esrb_violence_ref'])


class TestUpdateCerts(TestCase):

    @responses.activate
    def test_publish(self):
        setup_mock_response('UpdateCerts')
        app = app_factory()
        IARCCert.objects.create(
            app=app, cert_id='adb3261bc6574fd2a057bc9f85310b80')
        res = publish(app.pk)
        eq_(res['ResultList'][0]['ResultCode'], 'Success')
        eq_(len(responses.calls), 1)
        eq_(responses.calls[0].request.headers.get('StorePassword'),
            settings.IARC_V2_STORE_PASSWORD)
        eq_(responses.calls[0].request.headers.get('StoreID'),
            settings.IARC_V2_STORE_ID)
        eq_(json.loads(responses.calls[0].request.body), {
            'UpdateList': [{
                'Action': 'Publish',
                'CertID': 'adb3261b-c657-4fd2-a057-bc9f85310b80'
            }]
        })

    @responses.activate
    def test_publish_no_cert(self):
        res = publish(42)
        eq_(res, None)
        eq_(len(responses.calls), 0)

    @responses.activate
    def test_unpublish(self):
        setup_mock_response('UpdateCerts')
        app = app_factory()
        IARCCert.objects.create(
            app=app, cert_id='adb3261bc6574fd2a057bc9f85310b80')
        res = unpublish(app.pk)
        eq_(res['ResultList'][0]['ResultCode'], 'Success')
        eq_(len(responses.calls), 1)
        eq_(responses.calls[0].request.headers.get('StorePassword'),
            settings.IARC_V2_STORE_PASSWORD)
        eq_(responses.calls[0].request.headers.get('StoreID'),
            settings.IARC_V2_STORE_ID)
        eq_(json.loads(responses.calls[0].request.body), {
            'UpdateList': [{
                'Action': 'RemoveProduct',
                'CertID': 'adb3261b-c657-4fd2-a057-bc9f85310b80'
            }]
        })

    @responses.activate
    def test_unpublish_no_cert(self):
        res = unpublish(42)
        eq_(res, None)
        eq_(len(responses.calls), 0)


class TestSearchCertsAndAttachToCert(TestCase):
    def test_iarc_app_data(self):
        self.app = app_factory()
        self.profile = user_factory()
        self.app.addonuser_set.create(user=self.profile)
        eq_(_iarc_app_data(self.app),
            {'StoreProductID': self.app.guid,
             'StoreProductURL': absolutify(self.app.get_url_path()),
             'EmailAddress': self.profile.email,
             'CompanyName': u'',
             'StoreDeveloperID': self.app.pk,
             'DeveloperEmail': self.profile.email,
             'Publish': True,
             'ProductName': unicode(self.app.name)})

    def test_iarc_app_data_not_public(self):
        self.app = app_factory()
        self.profile = user_factory()
        self.app.addonuser_set.create(user=self.profile)
        with mock.patch.object(self.app, 'is_public') as is_public_mock:
            is_public_mock.return_value = False
            eq_(_iarc_app_data(self.app),
                {'StoreProductID': self.app.guid,
                 'StoreProductURL': absolutify(self.app.get_url_path()),
                 'EmailAddress': self.profile.email,
                 'CompanyName': u'',
                 'StoreDeveloperID': self.app.pk,
                 'DeveloperEmail': self.profile.email,
                 'Publish': False,
                 'ProductName': unicode(self.app.name)})

    @responses.activate
    def test_search_cert_error(self):
        setup_mock_response('SearchCerts', data='<!DOCTYPE html>error')
        serializer = search_cert(mock.Mock(), unicode(uuid4()))
        eq_(serializer.is_valid(), False)

    @responses.activate
    def test_search_cert_uuid_hex_string_w_separators(self):
        setup_mock_response('SearchCerts')
        fake_cert_id = unicode(uuid4())
        serializer = search_cert(mock.Mock(), fake_cert_id)
        eq_(serializer.is_valid(), True)
        eq_(len(responses.calls), 1)
        eq_(responses.calls[0].request.headers.get('StorePassword'),
            settings.IARC_V2_STORE_PASSWORD)
        eq_(responses.calls[0].request.headers.get('StoreID'),
            settings.IARC_V2_STORE_ID)
        eq_(json.loads(responses.calls[0].request.body), {
            'CertID': fake_cert_id
        })

    @responses.activate
    def test_search_cert_uuid_hex_string(self):
        setup_mock_response('SearchCerts')
        fake_cert = uuid4()
        serializer = search_cert(mock.Mock(), fake_cert.get_hex())
        eq_(serializer.is_valid(), True)
        eq_(len(responses.calls), 1)
        eq_(responses.calls[0].request.headers.get('StorePassword'),
            settings.IARC_V2_STORE_PASSWORD)
        eq_(responses.calls[0].request.headers.get('StoreID'),
            settings.IARC_V2_STORE_ID)
        eq_(json.loads(responses.calls[0].request.body), {
            'CertID': unicode(fake_cert)
        })

    @responses.activate
    def test_attach_to_cert_uuid_hex_string_w_separators(
            self):
        setup_mock_response('AttachToCert')
        fake_app = app_factory()
        fake_cert_id = unicode(uuid4())
        data = _attach_to_cert(fake_app, fake_cert_id)
        eq_(data,
            {'ResultCode': 'Success', 'ErrorMessage': None, 'ErrorID': None})
        expected_json = _iarc_app_data(fake_app)
        expected_json['CertID'] = fake_cert_id
        eq_(len(responses.calls), 1)
        eq_(responses.calls[0].request.headers.get('StorePassword'),
            settings.IARC_V2_STORE_PASSWORD)
        eq_(responses.calls[0].request.headers.get('StoreID'),
            settings.IARC_V2_STORE_ID)
        eq_(json.loads(responses.calls[0].request.body), expected_json)

    @responses.activate
    def test_attach_to_cert_uuid_hex_string(self):
        setup_mock_response('AttachToCert')
        fake_app = app_factory()
        fake_cert = uuid4()
        data = _attach_to_cert(fake_app, fake_cert.get_hex())
        eq_(data,
            {'ResultCode': 'Success', 'ErrorMessage': None, 'ErrorID': None})
        expected_json = _iarc_app_data(fake_app)
        expected_json['CertID'] = unicode(fake_cert)
        eq_(len(responses.calls), 1)
        eq_(responses.calls[0].request.headers.get('StorePassword'),
            settings.IARC_V2_STORE_PASSWORD)
        eq_(responses.calls[0].request.headers.get('StoreID'),
            settings.IARC_V2_STORE_ID)
        eq_(json.loads(responses.calls[0].request.body), expected_json)

    @responses.activate
    def test_search_and_attach_cert(self):
        setup_mock_response('AttachToCert')
        setup_mock_response('SearchCerts')

        app = app_factory()
        cert_id = 'adb3261b-c657-4fd2-a057-bc9f85310b80'
        data = search_and_attach_cert(app, cert_id)
        eq_(data,
            {'ResultCode': 'Success', 'ErrorMessage': None, 'ErrorID': None})
        eq_(UUID(app.iarc_cert.cert_id), UUID(cert_id))
        self.assertSetEqual(
            app.rating_descriptors.to_keys(),
            ['has_classind_lang', 'has_generic_parental_guidance_recommended',
             'has_pegi_parental_guidance_recommended'])
        self.assertSetEqual(
            app.rating_interactives.to_keys(),
            ['has_shares_location', 'has_digital_purchases',
             'has_users_interact'])
        eq_(app.get_content_ratings_by_body(),
            {'generic': '12', 'esrb': '13', 'classind': '12', 'usk': '12',
             'pegi': 'parental-guidance'})

    @responses.activate
    def test_search_and_attach_cert_invalid(self):
        setup_mock_response('SearchCerts', '{}')  # Invalid data.
        setup_mock_response('AttachToCert')
        app = app_factory()
        cert_id = 'adb3261b-c657-4fd2-a057-bc9f85310b80'
        with self.assertRaises(IARCException):
            search_and_attach_cert(app, cert_id)

        # Just to make sure we didn't do anything. There should have been only
        # one call to SearchCerts, none to AttachToCert.
        eq_(len(responses.calls), 1)
        eq_(RatingDescriptors.objects.filter(addon=app).exists(), False)
        eq_(RatingInteractives.objects.filter(addon=app).exists(), False)
        eq_(IARCCert.objects.filter(app=app).exists(), False)
        eq_(app.content_ratings.count(), 0)

    @responses.activate
    def test_refresh(self):
        setup_mock_response('SearchCerts')
        cert = UUID('adb3261b-c657-4fd2-a057-bc9f85310b80')
        app = app_factory()
        IARCCert.objects.create(app=app, cert_id=cert.get_hex())
        refresh(app)
        eq_(len(responses.calls), 1)
        eq_(responses.calls[0].request.headers.get('StorePassword'),
            settings.IARC_V2_STORE_PASSWORD)
        eq_(responses.calls[0].request.headers.get('StoreID'),
            settings.IARC_V2_STORE_ID)
        eq_(json.loads(responses.calls[0].request.body), {
            'CertID': unicode(cert)
        })

        # Compare with mock data. Force reload using .objects.get in order to
        # properly reset the related objects caching.
        app = Webapp.objects.get(pk=app.pk)
        self.assertSetEqual(
            app.rating_descriptors.to_keys(),
            ['has_classind_lang', 'has_generic_parental_guidance_recommended',
             'has_pegi_parental_guidance_recommended'])
        self.assertSetEqual(
            app.rating_interactives.to_keys(),
            ['has_shares_location', 'has_digital_purchases',
             'has_users_interact'])
        eq_(app.content_ratings.all()[0].get_rating_class(), CLASSIND_12)


class TestSearchCertsAndAttachToCertWithTransaction(TransactionTestCase):
    # This test class needs to be a real transaction to test rollback behavior.

    @responses.activate
    def test_search_and_attach_cert_error(self):
        setup_mock_response('SearchCerts')
        setup_mock_response('AttachToCert', '{}')  # Invalid data.

        app = app_factory()
        cert_id = 'adb3261b-c657-4fd2-a057-bc9f85310b80'
        with self.assertRaises(IARCException):
            search_and_attach_cert(app, cert_id)

        # Both requests were made.
        eq_(len(responses.calls), 2)
        eq_(responses.calls[0].request.url,
            urljoin(settings.IARC_V2_SERVICE_ENDPOINT, 'SearchCerts'))
        eq_(responses.calls[1].request.url,
            urljoin(settings.IARC_V2_SERVICE_ENDPOINT, 'AttachToCert'))

        # Just to make sure we didn't save anything.
        eq_(RatingDescriptors.objects.filter(addon=app).exists(), False)
        eq_(RatingInteractives.objects.filter(addon=app).exists(), False)
        eq_(IARCCert.objects.filter(app=app).exists(), False)
        eq_(app.content_ratings.count(), 0)
