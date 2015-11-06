from django.test.client import RequestFactory

import mock
from nose.tools import eq_

import mkt.site.tests
from mkt.constants.features import FeatureProfile
from mkt.features.utils import load_feature_profile


class TestLoadFeatureProfile(mkt.site.tests.TestCase):
    def setUp(self):
        super(TestLoadFeatureProfile, self).setUp()
        self.profile = FeatureProfile(apps=True)
        self.signature = self.profile.to_signature()

    def test_does_nothing_on_desktop(self):
        request = RequestFactory().get('/?dev=desktop&pro=%s' % self.signature)
        load_feature_profile(request)
        eq_(request.feature_profile, None)

    def test_does_nothing_without_dev_param(self):
        request = RequestFactory().get('/?pro=%s' % self.signature)
        load_feature_profile(request)
        eq_(request.feature_profile, None)
        request = RequestFactory().get(
            '/?device=mobilepro=%s' % self.signature)
        load_feature_profile(request)
        eq_(request.feature_profile, None)

    def test_does_nothing_without_profile_signature(self):
        request = RequestFactory().get('/?dev=firefoxos')
        load_feature_profile(request)
        eq_(request.feature_profile, None)

    def test_does_nothing_if_invalid_profile_signature_is_passed(self):
        request = RequestFactory().get('/?dev=firefoxos&pro=whatever')
        load_feature_profile(request)
        eq_(request.feature_profile, None)

    def test_works(self):
        request = RequestFactory().get(
            '/?dev=firefoxos&pro=%s' % self.signature)
        load_feature_profile(request)
        eq_(request.feature_profile.to_list(), self.profile.to_list())

    @mock.patch('mkt.features.utils.FeatureProfile.from_signature')
    def test_caching_on_request_property(self, from_signature_mock):
        fake_feature_profile = object()
        from_signature_mock.return_value = fake_feature_profile
        request = RequestFactory().get(
            '/?dev=firefoxos&pro=%s' % self.signature)
        load_feature_profile(request)
        eq_(request.feature_profile, fake_feature_profile)

        from_signature_mock.return_value = None
        load_feature_profile(request)
        # Should not be None thanks to the property caching.
        eq_(request.feature_profile, fake_feature_profile)
