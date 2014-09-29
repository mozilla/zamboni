import mock
from nose.tools import eq_, ok_
from requests.exceptions import RequestException

from mkt.inapp.serializers import InAppProductSerializer

from .test_views import BaseInAppProductViewSetTests


class TestInAppProductSerializer(BaseInAppProductViewSetTests):

    def post(self, **kw):
        if 'data' not in kw:
            kw['data'] = self.valid_in_app_product_data
        return InAppProductSerializer(**kw)

    def assert_logo_error(self, serializer):
        eq_(serializer.errors['logo_url'],
            ['Product logo must be a 64x64 image. '
             'Check that the URL is correct.'])

    def test_valid(self):
        self.mock_logo_url()
        serializer = self.post()
        ok_(serializer.is_valid())

    def test_no_logo_url(self):
        product_data = dict(self.valid_in_app_product_data)
        del product_data['logo_url']
        serializer = self.post(data=product_data)
        ok_(serializer.is_valid(), serializer.errors)

    def test_wrong_logo_size(self):
        self.mock_logo_url(resource='logo-128.png')
        serializer = self.post()
        ok_(not serializer.is_valid())
        self.assert_logo_error(serializer)

    def test_bad_logo_url(self):
        self.mock_logo_url(url_side_effect=RequestException('404'))
        serializer = self.post()
        ok_(not serializer.is_valid())
        self.assert_logo_error(serializer)

    def test_logo_image_error(self):
        self.mock_logo_url()

        p = mock.patch('mkt.inapp.serializers.Image.open')
        opener = p.start()
        self.addCleanup(p.stop)
        img = mock.Mock()
        img.verify.side_effect = ValueError('not an image')
        opener.return_value = img

        serializer = self.post()
        ok_(not serializer.is_valid())
        self.assert_logo_error(serializer)

    def test_logo_url_to_big(self):
        self.mock_logo_url()
        serializer = self.post()
        with self.settings(MAX_INAPP_IMAGE_SIZE=2):
            ok_(not serializer.is_valid())
        self.assert_logo_error(serializer)

    def test_create_ftp_scheme(self):
        product_data = dict(self.valid_in_app_product_data)
        product_data['logo_url'] = 'ftp://example.com/awesome.png'
        serializer = self.post(data=product_data)
        ok_(not serializer.is_valid())
        eq_(serializer.errors['logo_url'],
            ['Scheme should be one of http, https.'])
