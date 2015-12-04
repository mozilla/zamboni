# -*- coding: utf-8 -*-
import mock
from nose.tools import eq_
from rest_framework.exceptions import ParseError
from uuid import UUID


import mkt.site.tests
from lib.iarc.serializers import IARCV2RatingListSerializer
from mkt.constants import ratingsbodies
from mkt.constants.applications import DEVICE_GAIA
from mkt.constants.base import STATUS_NULL, STATUS_PENDING
from mkt.site.utils import app_factory
from mkt.webapps.models import IARCCert


class TestIARCV2RatingListSerializer(mkt.site.tests.TestCase):
    def setUp(self):
        self.create_switch('iarc-upgrade-v2')

    def test_validate_no_data(self):
        data = {}
        serializer = IARCV2RatingListSerializer(mock.Mock(), data)
        eq_(serializer.is_valid(), False)
        eq_(serializer.validated_data, None)
        eq_(serializer.errors, {'RatingList': 'This field is required.'})

    def test_validate_no_cert_id(self):
        data = {
            'RatingList': [{
                'RatingAuthorityShortText': 'Generic',
                'AgeRatingText': '12+',
            }]
        }
        serializer = IARCV2RatingListSerializer(mock.Mock(), data)
        eq_(serializer.is_valid(), False)
        eq_(serializer.validated_data, None)
        eq_(serializer.errors, {'CertID': 'This field is required.'})

    def test_validate_invalid_cert_id(self):
        data = {
            'CertID': 'lol',
            'RatingList': [{
                'RatingAuthorityShortText': 'Generic',
                'AgeRatingText': '12+',
            }]
        }
        serializer = IARCV2RatingListSerializer(mock.Mock(), data)
        eq_(serializer.is_valid(), False)
        eq_(serializer.validated_data, None)
        eq_(serializer.errors,
            {'CertID': 'badly formed hexadecimal UUID string'})

    def test_validate_no_rating_list(self):
        data = {'CertID': 'ae52b2d2-d4f7-4ebb-aade-28aa9795c5db'}
        serializer = IARCV2RatingListSerializer(mock.Mock(), data)
        eq_(serializer.is_valid(), False)
        eq_(serializer.validated_data, None)
        eq_(serializer.errors, {'RatingList': 'This field is required.'})

    def test_validate_rating_list_empty(self):
        data = {
            'CertID': 'ae52b2d2-d4f7-4ebb-aade-28aa9795c5db',
            'RatingList': [],
        }
        serializer = IARCV2RatingListSerializer(mock.Mock(), data)
        eq_(serializer.is_valid(), False)
        eq_(serializer.validated_data, None)
        eq_(serializer.errors, {'RatingList': 'This field is required.'})

    def test_validate_with_unknown_body(self):
        data = {
            'CertID': 'ae52b2d2-d4f7-4ebb-aade-28aa9795c5db',
            'RatingList': [
                {
                    'RatingAuthorityShortText': 'Blah',
                    'AgeRatingText': '12+',
                }
            ]
        }
        serializer = IARCV2RatingListSerializer(None, data)
        # The unknown body should *not* generate an error.
        eq_(serializer.is_valid(), True)
        eq_(serializer.validated_data,
            {'cert_id': UUID('ae52b2d2-d4f7-4ebb-aade-28aa9795c5db'),
             'descriptors': set([]), 'interactives': set([]), 'ratings': {}})
        eq_(serializer.errors, {})

    def test_validate_multiple_bodies_with_redundant_info(self):
        data = {
            'CertID': 'ae52b2d2-d4f7-4ebb-aade-28aa9795c5db',
            'RatingList': [
                {
                    'RatingAuthorityShortText': 'Generic',
                    'AgeRatingText': '12+',
                    'DescriptorList': [{'DescriptorText': 'PEGI_Violence'}],
                    'InteractiveElementList': [
                        {'InteractiveElementText': 'IE_UsersInteract'},
                        {'InteractiveElementText': 'IE_SharesLocation'},
                        {'InteractiveElementText': 'IE_DigitalPurchases'}
                    ]
                },
                {
                    'RatingAuthorityShortText': 'PEGI',
                    'AgeRatingText': '12+',
                    'DescriptorList': [
                        {'DescriptorText': 'PEGI_Violence'},
                        {'DescriptorText': 'PEGI_Online'},
                    ],
                    'InteractiveElementList': [
                        {'InteractiveElementText': 'IE_UsersInteract'},
                        {'InteractiveElementText': 'IE_DigitalPurchases'}
                    ]
                },
                {
                    'RatingAuthorityShortText': 'ESRB',
                    'AgeRatingText': 'Teen',
                    'DescriptorList': [],
                    'InteractiveElementList': []
                },
            ]
        }
        expected_data = {
            'cert_id': UUID('ae52b2d2-d4f7-4ebb-aade-28aa9795c5db'),
            'descriptors': set(['has_generic_violence',
                                'has_pegi_online',
                                'has_pegi_violence']),
            'interactives': set(['has_shares_location',
                                 'has_digital_purchases',
                                 'has_users_interact']),
            'ratings': {
                ratingsbodies.ESRB: ratingsbodies.ESRB_T,
                ratingsbodies.GENERIC: ratingsbodies.GENERIC_12,
                ratingsbodies.PEGI: ratingsbodies.PEGI_12,
            },
        }
        serializer = IARCV2RatingListSerializer(None, data)
        eq_(serializer.is_valid(), True)
        eq_(serializer.errors, {})
        eq_(serializer.validated_data['cert_id'], expected_data['cert_id'])
        self.assertSetEqual(
            serializer.validated_data['descriptors'],
            expected_data['descriptors'])
        self.assertSetEqual(
            serializer.validated_data['interactives'],
            expected_data['interactives'])
        eq_(serializer.validated_data['ratings'], expected_data['ratings'])
        return serializer

    def test_save_with_no_instance(self):
        serializer = IARCV2RatingListSerializer(data={})
        with self.assertRaises(ValueError):
            serializer.save()

    @mock.patch.object(IARCV2RatingListSerializer, 'is_valid')
    def test_save_with_invalid_data(self, is_valid_mock):
        is_valid_mock.return_value = False
        serializer = IARCV2RatingListSerializer(instance=object())
        with self.assertRaises(ParseError):
            serializer.save()

    def test_save_success_mocked(self):
        serializer = self.test_validate_multiple_bodies_with_redundant_info()
        serializer.object = mock.Mock()
        serializer.save()

        eq_(serializer.object.set_iarc_certificate.call_count, 1)
        eq_(serializer.object.set_iarc_certificate.call_args[0][0],
            serializer.validated_data['cert_id'])

        eq_(serializer.object.set_descriptors.call_count, 1)
        eq_(serializer.object.set_descriptors.call_args[0][0],
            serializer.validated_data['descriptors'])

        eq_(serializer.object.set_interactives.call_count, 1)
        eq_(serializer.object.set_interactives.call_args[0][0],
            serializer.validated_data['interactives'])

        eq_(serializer.object.set_content_ratings.call_count, 1)
        eq_(serializer.object.set_content_ratings.call_args[0][0],
            serializer.validated_data['ratings'])

    def test_save_success(self):
        """Like test_save_success_mocked() above, but more of an integration
        test with no mocks, to make sure the whole process works."""
        # Start by making an "almost" complete app, that has everything set up
        # except ratings.
        app = app_factory(categories=['games'], status=STATUS_NULL,
                          support_email='test@example.com')
        app.addondevicetype_set.create(device_type=DEVICE_GAIA.id)
        app.previews.create()
        eq_(app.is_fully_complete(ignore_ratings=True), True)
        # Then validate and save normally.
        serializer = self.test_validate_multiple_bodies_with_redundant_info()
        serializer.object = app
        serializer.save()

        # Now check that everything went ok.
        app.reload()
        eq_(app.status, STATUS_PENDING)
        eq_(app.is_fully_complete(), True)
        eq_(UUID(app.iarc_cert.cert_id), serializer.validated_data['cert_id'])
        eq_(app.get_content_ratings_by_body(),
            {'generic': '12', 'esrb': '13', 'pegi': '12'})
        self.assertSetEqual(
            app.rating_descriptors.to_keys(),
            ['has_pegi_violence', 'has_generic_violence', 'has_pegi_online'])
        self.assertSetEqual(
            app.rating_interactives.to_keys(),
            ['has_shares_location', 'has_digital_purchases',
             'has_users_interact'])

    def test_save_success_already_had_cert(self):
        app = app_factory()
        cert = IARCCert.objects.create(app=app, modified=self.days_ago(42))
        serializer = self.test_validate_multiple_bodies_with_redundant_info()
        serializer.object = app
        serializer.validated_data['cert_id'] = UUID(cert.cert_id)
        serializer.save()

        cert.reload()
        self.assertCloseToNow(cert.modified)
        eq_(IARCCert.objects.count(), 1)
