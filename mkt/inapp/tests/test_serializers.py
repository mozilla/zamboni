from nose.tools import eq_, ok_

import amo.tests
from mkt.inapp.serializers import InAppProductSerializer
from mkt.site.fixtures import fixture
from mkt.webapps.models import Webapp
from mkt.prices.models import Price


class TestInAppProductSerializer(amo.tests.TestCase):
    fixtures = fixture('webapp_337141', 'prices')

    def setUp(self):
        self.webapp = Webapp.objects.get(pk=337141)
        price = Price.objects.all()[0]
        self.valid_product_data = {
            'name': 'Purple Gems',
            'logo_url': 'https://marketplace.firefox.com/rocket.png',
            'price_id': price.id,
        }

    def test_valid(self):
        serializer = InAppProductSerializer(data=self.valid_product_data)
        ok_(serializer.is_valid())

    def test_no_logo_url(self):
        product_data = dict(self.valid_product_data)
        del product_data['logo_url']
        serializer = InAppProductSerializer(data=product_data)
        ok_(serializer.is_valid())

    def test_create_ftp_scheme(self):
        product_data = dict(self.valid_product_data)
        product_data['logo_url'] = 'ftp://example.com/awesome.png'
        serializer = InAppProductSerializer(data=product_data)
        ok_(not serializer.is_valid())
        eq_(serializer.errors['logo_url'],
            ['Scheme should be one of http, https.'])
