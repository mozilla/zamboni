import json

from django.core.urlresolvers import reverse

from nose.tools import eq_
from rest_framework import status

import amo.tests
from mkt.users.models import UserProfile

from mkt.api.tests.test_oauth import JSONClient, RestOAuthClient
from mkt.api.models import Access, generate
from mkt.inapp.models import InAppProduct
from mkt.site.fixtures import fixture
from mkt.webapps.models import Webapp
from mkt.prices.models import Price


class BaseInAppProductViewSetTests(amo.tests.TestCase):

    def setUp(self):
        self.webapp = Webapp.objects.get(pk=337141)
        self.webapp.update(app_domain='app://rad-app.com',
                           is_packaged=True)
        price = Price.objects.all()[0]
        self.valid_in_app_product_data = {
            'name': 'Purple Gems',
            'logo_url': 'https://marketplace.firefox.com/rocket.png',
            'price_id': price.id,
        }

    def setup_client(self, user):
        access = Access.objects.create(key='test_oauth_key_owner',
                                       secret=generate(), user=user)
        return RestOAuthClient(access)

    def list_url(self):
        return reverse('in-app-products-list',
                       kwargs={'origin': self.webapp.origin})

    def detail_url(self, pk):
        return reverse('in-app-products-detail',
                       kwargs={'origin': self.webapp.origin,
                               'pk': pk})

    def create_product(self):
        product_data = {'webapp': self.webapp}
        product_data.update(self.valid_in_app_product_data)
        return InAppProduct.objects.create(**product_data)

    def get(self, url):
        return self.client.get(url)

    def post(self, url, data):
        return self.client.post(url, json.dumps(data),
                                content_type='application/json')

    def put(self, url, data):
        return self.client.put(url, json.dumps(data),
                               content_type='application/json')

    def delete(self, url):
        return self.client.delete(url)


class TestInAppProductViewSetAuthorized(BaseInAppProductViewSetTests):
    fixtures = fixture('webapp_337141', 'prices')

    def setUp(self):
        super(TestInAppProductViewSetAuthorized, self).setUp()
        user = self.webapp.authors.all()[0]
        self.client = self.setup_client(user)

    def test_create(self):
        response = self.post(self.list_url(), self.valid_in_app_product_data)
        eq_(response.status_code, status.HTTP_201_CREATED)
        eq_(response.json['name'], 'Purple Gems')

    def test_update(self):
        product = self.create_product()
        self.valid_in_app_product_data['name'] = 'Orange Gems'
        response = self.put(self.detail_url(product.id),
                            self.valid_in_app_product_data)
        eq_(response.status_code, status.HTTP_200_OK)
        eq_(response.json['name'], 'Orange Gems')
        eq_(response.json['name'], product.reload().name)

    def test_delete(self):
        product = self.create_product()
        delete_response = self.delete(self.detail_url(product.id))
        eq_(delete_response.status_code, status.HTTP_403_FORBIDDEN)


class TestInAppProductViewSetUnauthorized(BaseInAppProductViewSetTests):
    fixtures = fixture('user_999', 'webapp_337141', 'prices')

    def setUp(self):
        super(TestInAppProductViewSetUnauthorized, self).setUp()
        user = UserProfile.objects.get(id=999)
        self.client = self.setup_client(user)

    def test_create(self):
        response = self.post(self.list_url(),
                             self.valid_in_app_product_data)
        eq_(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update(self):
        product = self.create_product()
        self.valid_in_app_product_data['name'] = 'Orange Gems'
        response = self.put(self.detail_url(product.id),
                            self.valid_in_app_product_data)
        eq_(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list(self):
        product1 = self.create_product()
        product2 = self.create_product()
        response = self.get(self.list_url())
        eq_(response.status_code, status.HTTP_200_OK)
        eq_(sorted([p['id'] for p in response.json['objects']]),
            [product1.id, product2.id])

    def test_detail(self):
        product = self.create_product()
        response = self.get(self.detail_url(product.id))
        eq_(response.status_code, status.HTTP_200_OK)
        eq_(response.json['id'], product.id)

    def test_delete(self):
        product = self.create_product()
        response = self.delete(self.detail_url(product.id))
        eq_(response.status_code, status.HTTP_403_FORBIDDEN)


class TestInAppProductViewSetAuthorizedCookie(BaseInAppProductViewSetTests):
    fixtures = fixture('user_999', 'webapp_337141', 'prices')

    def setUp(self):
        super(TestInAppProductViewSetAuthorizedCookie, self).setUp()
        user = UserProfile.objects.get(id=31337)
        self.login(user)

    def test_create(self):
        response = self.post(self.list_url(),
                             self.valid_in_app_product_data)
        eq_(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update(self):
        product = self.create_product()
        self.valid_in_app_product_data['name'] = 'Orange Gems'
        response = self.put(self.detail_url(product.id),
                            self.valid_in_app_product_data)
        eq_(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete(self):
        product = self.create_product()
        response = self.delete(self.detail_url(product.id))
        eq_(response.status_code, status.HTTP_403_FORBIDDEN)


class TestStubInAppProductViewSet(BaseInAppProductViewSetTests):
    fixtures = fixture('user_999', 'webapp_337141', 'prices2')

    def setUp(self):
        super(TestStubInAppProductViewSet, self).setUp()
        self.client = JSONClient()

    def list_url(self):
        return reverse('stub-in-app-products-list')

    def objects(self, res):
        return sorted(res.json['objects'], key=lambda d: d['name'])

    def test_get_when_stubs_dont_exist(self):
        res = self.get(self.list_url())
        eq_(res.status_code, status.HTTP_200_OK)
        objects = self.objects(res)
        eq_(objects[0]['name'], 'Kiwi')
        eq_(objects[0]['price_id'], 1)
        eq_(objects[1]['name'], 'Unicorn')
        eq_(objects[1]['price_id'], 2)

    def test_get_existing_stubs(self):
        stub = InAppProduct.objects.create(stub=True,
                                           name='Test Product',
                                           price=Price.objects.all()[0])

        res = self.get(self.list_url())
        eq_(res.status_code, status.HTTP_200_OK)
        objects = self.objects(res)
        eq_(objects[0]['name'], stub.name)
        eq_(objects[0]['price_id'], stub.price.pk)
        eq_(InAppProduct.objects.all().count(), 1,
            'No new stubs should have been created')
