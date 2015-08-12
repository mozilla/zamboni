import itertools
from collections import OrderedDict

from django.conf import settings

import mock
from nose.tools import eq_, ok_

import mkt.site.tests
from mkt.constants.features import (APP_FEATURES, FeaturesBitField,
                                    FeatureProfile)


MOCK_APP_FEATURES_LIMIT = 45
MOCK_APP_FEATURES = OrderedDict(
    itertools.islice(APP_FEATURES.iteritems(), MOCK_APP_FEATURES_LIMIT))


class TestFeaturesMixin(object):
    features = 0x110022000000
    signature = '110022000000.%d.%d' % (
        MOCK_APP_FEATURES_LIMIT, settings.APP_FEATURES_VERSION)
    expected_features = ['apps', 'proximity', 'light_events', 'vibrate']
    base64_signature = '=EYAIAAAA.%d.%d' % (
        MOCK_APP_FEATURES_LIMIT, settings.APP_FEATURES_VERSION)

    def _test_profile_values(self, profile):
        for k, v in profile.iteritems():
            if v:
                ok_(k in self.expected_features,
                    '"%s" is true in profile but not in expected_features' % k)
            else:
                ok_(k not in self.expected_features,
                    '"%s" is false in profile but is in expected_features' % k)

    def _test_profile(self, profile):
        eq_(profile.to_int(), self.features)
        eq_(profile.to_signature(), self.signature)
        self._test_profile_values(profile)


@mock.patch('mkt.constants.features.APP_FEATURES', MOCK_APP_FEATURES)
class TestFeatureProfileFixed(TestFeaturesMixin, mkt.site.tests.TestCase):
    def test_init(self):
        profile = FeatureProfile(**dict(
            (f, True) for f in self.expected_features))
        eq_(profile.to_signature(), self.signature)
        eq_(profile.to_int(), self.features)

    def test_from_int(self):
        profile = FeatureProfile.from_int(self.features)
        self._test_profile(profile)

    def test_from_int_all_false(self):
        self.features = 0
        self.signature = '0.%d.%d' % (
            MOCK_APP_FEATURES_LIMIT, settings.APP_FEATURES_VERSION)
        self.expected_features = []
        self.test_from_int()

    def test_from_list(self):
        bools = [False] * MOCK_APP_FEATURES_LIMIT
        bools[0] = True  # apps
        bools[4] = True  # light events
        bools[15] = True  # proximity
        bools[19] = True  # vibrate
        profile = FeatureProfile.from_list(bools)
        self._test_profile(profile)

    def test_from_signature(self):
        profile = FeatureProfile.from_signature(self.signature)
        self._test_profile(profile)

    def test_from_base64(self):
        profile = FeatureProfile.from_signature(self.base64_signature)
        self._test_profile(profile)

    def _test_kwargs(self, prefix):
        profile = FeatureProfile.from_int(self.features)
        kwargs = profile.to_kwargs(prefix=prefix)

        ok_(all([k.startswith(prefix) for k in kwargs.keys()]))
        eq_(kwargs.values().count(False), bin(self.features)[2:].count('0'))
        eq_(len(kwargs.values()),
            len(MOCK_APP_FEATURES) - len(self.expected_features))

    def test_to_kwargs(self):
        self._test_kwargs('')
        self._test_kwargs('prefix_')

    def test_to_base64(self):
        profile = FeatureProfile.from_int(self.features)
        signature = profile.to_base64_signature()
        eq_(signature, self.base64_signature)


class TestFeatureProfileDynamic(TestFeaturesMixin, mkt.site.tests.TestCase):
    def test_from_int_limit(self):
        profile = FeatureProfile.from_int(
            self.features, limit=MOCK_APP_FEATURES_LIMIT)
        self._test_profile_values(profile)

    def test_from_old_signature(self):
        profile = FeatureProfile.from_signature(self.signature)
        self._test_profile_values(profile)
        new_signature = profile.to_signature()
        ok_(new_signature != self.signature)
        profile = FeatureProfile.from_signature(new_signature)
        self._test_profile_values(profile)


class TestFeaturesBitField(mkt.site.tests.TestCase):
    test_data = [True, False, False, False, False, False, False, True, True]

    def test_basic(self):
        bitfield = FeaturesBitField(8)
        eq_(bitfield.values, [0])
        bitfield = FeaturesBitField(9)
        eq_(bitfield.values, [0, 0])
        bitfield = FeaturesBitField(16)
        eq_(bitfield.values, [0, 0])
        bitfield = FeaturesBitField(53)
        eq_(bitfield.values, [0, 0, 0, 0, 0, 0, 0])

    def test_basic_values(self):
        bitfield = FeaturesBitField(8, values=[0, 1, 3])
        eq_(bitfield.values, [0, 1, 3])

    def test_set(self):
        bitfield = FeaturesBitField(9)
        bitfield.set(0, True)
        eq_(bitfield.values, [1, 0])
        bitfield.set(1, True)
        eq_(bitfield.values, [3, 0])
        bitfield.set(8, True)
        eq_(bitfield.values, [3, 1])

    def test_get(self):
        bitfield = FeaturesBitField(9)
        eq_(bitfield.get(0), False)
        bitfield.set(0, True)
        eq_(bitfield.get(0), True)

        eq_(bitfield.get(8), False)
        bitfield.set(8, True)
        eq_(bitfield.get(8), True)

    def test_to_list(self):
        bitfield = FeaturesBitField(9)
        bitfield.set(0, True)
        bitfield.set(7, True)
        bitfield.set(8, True)
        eq_(bitfield.to_list(), self.test_data)

    def test_from_list(self):
        bitfield = FeaturesBitField.from_list(self.test_data)
        eq_(bitfield.values, [129, 1])
        eq_(bitfield.to_list(), self.test_data)

    def test_to_base64(self):
        bitfield = FeaturesBitField.from_list(self.test_data)
        eq_(bitfield.to_base64(), 'gQE=')

    def test_from_base64(self):
        bitfield = FeaturesBitField.from_base64('gQE=', len(self.test_data))
        eq_(bitfield.to_list(), self.test_data)
        eq_(bitfield.to_base64(), 'gQE=')

    def test_from_base64_full_of_truth(self):
        bitfield = FeaturesBitField.from_base64('/wE=', len(self.test_data))
        eq_(bitfield.to_list(), [True] * 9)
        eq_(bitfield.values, [255, 1])
        eq_(bitfield.to_base64(), '/wE=')

    def test_from_base64_full_of_lies(self):
        bitfield = FeaturesBitField.from_base64('AAA=', len(self.test_data))
        eq_(bitfield.to_list(), [False] * 9)
        eq_(bitfield.values, [0, 0])
        eq_(bitfield.to_base64(), 'AAA=')
