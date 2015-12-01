# -*- coding: utf-8 -*-
import mock
from nose.tools import eq_
from rest_framework.exceptions import ParseError

import mkt.site.tests
from mkt.constants import ratingsbodies
from lib.iarc.serializers import IARCV2RatingListSerializer


class TestIARCV2RatingListSerializer(mkt.site.tests.TestCase):
    def test_validate_no_rating_list(self):
        serializer = IARCV2RatingListSerializer(None, {})
        eq_(serializer.validated_data, None)
        eq_(serializer.is_valid(), False)

    def test_validate_rating_list_empty(self):
        serializer = IARCV2RatingListSerializer(None, {'RatingList': []})
        eq_(serializer.validated_data, None)
        eq_(serializer.is_valid(), False)

    def test_validate_with_unknown_body(self):
        data = {
            'RatingList': [
                {
                    'RatingAuthorityShortText': 'Blah',
                    'AgeRatingText': '12+',
                }
            ]
        }
        serializer = IARCV2RatingListSerializer(None, data)
        # The unknown body should not generate an error
        eq_(serializer.validated_data,
            {'descriptors': set([]), 'interactives': set([]), 'ratings': {}})
        eq_(serializer.is_valid(), True)

    def test_validate_multiple_bodies_with_redundant_info(self):
        data = {
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
        self.assertSetEqual(
            serializer.validated_data['descriptors'],
            expected_data['descriptors'])
        self.assertSetEqual(
            serializer.validated_data['interactives'],
            expected_data['interactives'])
        eq_(
            serializer.validated_data['ratings'],
            expected_data['ratings'])
        eq_(serializer.is_valid(), True)
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

    def test_save_success(self):
        serializer = self.test_validate_multiple_bodies_with_redundant_info()
        serializer.instance = mock.Mock()
        serializer.save()

        eq_(serializer.instance.set_descriptors.call_count, 1)
        eq_(serializer.instance.set_descriptors.call_args[0][0],
            serializer.validated_data['descriptors'])

        eq_(serializer.instance.set_interactives.call_count, 1)
        eq_(serializer.instance.set_interactives.call_args[0][0],
            serializer.validated_data['interactives'])

        eq_(serializer.instance.set_content_ratings.call_count, 1)
        eq_(serializer.instance.set_content_ratings.call_args[0][0],
            serializer.validated_data['ratings'])
