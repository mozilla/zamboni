# coding: utf-8
import json
import os

from django.conf import settings
from django.core.urlresolvers import reverse

import mock
from nose.tools import eq_
from rest_framework import status

import mkt.site.tests
from mkt.users.models import UserProfile

from mkt.api.tests.test_oauth import JSONClient, RestOAuthClient
from mkt.api.models import Access
from mkt.inapp.models import InAppProduct
from mkt.site.fixtures import fixture
from mkt.translations.models import Translation
from mkt.webapps.models import Webapp
from mkt.prices.models import Price


class BaseInAppProductViewSetTests(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141', 'prices')

    def setUp(self):
        self.webapp = Webapp.objects.get(pk=337141)
        self.webapp.update(app_domain='app://rad-app.com',
                           is_packaged=True)
        price = Price.objects.all()[0]

        self.valid_in_app_product_data = {
            'default_locale': 'en-us',
            'name': {'en-us': 'Purple Gems',
                     'pl': u'الأحجار الكريمة الأرجواني'},
            'logo_url': 'https://marketplace.firefox.com/rocket.png',
            'price_id': price.id,
        }

        p = mock.patch('mkt.inapp.serializers.requests')
        self.requests = p.start()
        self.addCleanup(p.stop)

        p = mock.patch.object(settings, 'LANGUAGES',
                              ('en-us', 'es', 'fr', 'pl'))
        p.start()
        self.addCleanup(p.stop)

    def setup_client(self, user):
        access = Access.objects.create(key='test_oauth_key_owner',
                                       secret='super secret', user=user)
        return RestOAuthClient(access)

    def mock_logo_url(self, resource='logo-64.png', url_side_effect=None):
        response = mock.Mock()
        img = open(os.path.join(os.path.dirname(__file__),
                                'resources', resource), 'rb')
        response.iter_content.return_value = [img.read()]
        if url_side_effect:
            response.iter_content.side_effect = url_side_effect
        self.addCleanup(img.close)
        self.requests.get.return_value = response

    def list_url(self):
        return reverse('in-app-products-list',
                       kwargs={'origin': self.webapp.origin})

    def detail_url(self, guid):
        return reverse('in-app-products-detail',
                       kwargs={'origin': self.webapp.origin,
                               'guid': guid})

    def create_product(self):
        product_data = {'webapp': self.webapp}
        product_data.update(self.valid_in_app_product_data)
        if isinstance(product_data['name'], basestring):
            product_data['name'] = json.loads(product_data['name'])
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


class AuthenticatedInAppProductTest(BaseInAppProductViewSetTests):

    def setUp(self):
        super(AuthenticatedInAppProductTest, self).setUp()
        self.mock_logo_url()
        user = self.webapp.authors.all()[0]
        self.client = self.setup_client(user)


class TestInAppProductViewSetAuthorized(AuthenticatedInAppProductTest):

    def all_locales(self, prod, attr):
        names = {}
        trans = getattr(prod, attr)
        for tr in Translation.objects.filter(id=trans.id):
            names[tr.locale] = unicode(tr)
        return names

    def test_create(self):
        response = self.post(self.list_url(), self.valid_in_app_product_data)
        eq_(response.status_code, status.HTTP_201_CREATED)
        eq_(response.json['name'], 'Purple Gems')

    def test_create_localized_names(self):
        data = self.valid_in_app_product_data.copy()
        name_data = data['name'].copy()
        response = self.post(self.list_url(), data)
        eq_(response.status_code, status.HTTP_201_CREATED)

        # TODO: use localized API output after bug 1070125.
        prod = InAppProduct.objects.get(guid=response.json['guid'])
        names = self.all_locales(prod, 'name')
        eq_(names['en-us'], name_data['en-us'])
        eq_(names['pl'], name_data['pl'])

    def test_missing_default_locale(self):
        data = self.valid_in_app_product_data.copy()
        data['name'] = {'en-us': 'English name'}
        data['default_locale'] = 'pl'  # no localization for this
        response = self.post(self.list_url(), data)
        eq_(response.status_code, 400,
            getattr(response, 'json', 'unexpected status'))

    def test_empty_default_locale(self):
        data = self.valid_in_app_product_data.copy()
        data['name'] = {'en-us': None}  # empty localization
        data['default_locale'] = 'en-us'
        response = self.post(self.list_url(), data)
        eq_(response.status_code, 400,
            getattr(response, 'json', 'unexpected status'))

    def test_update(self):
        product = self.create_product()
        data = self.valid_in_app_product_data.copy()
        data['name'] = {'en-us': 'Orange Gems'}
        data['active'] = False
        response = self.put(self.detail_url(product.guid), data)
        eq_(response.status_code, status.HTTP_200_OK)
        eq_(response.json['name'], 'Orange Gems')
        # Sanity check that the db was updated.
        eq_(response.json['name'], product.reload().name)
        eq_(response.json['active'], False)

    def test_update_locales(self):
        product = self.create_product()
        data = self.valid_in_app_product_data.copy()
        old_names = data['name'].copy()

        new_names = {'fr': 'French Gems',
                     'es': 'Spanish Gems',
                     'pl': None}
        data['name'] = new_names
        data['default_locale'] = 'fr'

        response = self.put(self.detail_url(product.guid), data)
        eq_(response.status_code, status.HTTP_200_OK,
            getattr(response, 'json', 'unexpected status'))

        product = product.reload()
        names = self.all_locales(product, 'name')

        eq_(names['fr'], new_names['fr'])
        eq_(names['es'], new_names['es'])
        # Localized string set to None is blank:
        eq_(names['pl'], '')
        # The old locale was not deleted or updated.
        # This is a bit weird but that's the status quo of translations.
        eq_(names['en-us'], old_names['en-us'])

    def test_delete(self):
        product = self.create_product()
        delete_response = self.delete(self.detail_url(product.guid))
        eq_(delete_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_filter(self):
        active = self.create_product()
        inactive = self.create_product()
        inactive.update(active=False)

        response = self.get(self.list_url())
        eq_(response.json['meta']['total_count'], 2)

        response = self.get(self.list_url() + '?active=1')
        eq_(response.json['meta']['total_count'], 1)
        eq_(response.json['objects'][0]['guid'], active.guid)

        response = self.get(self.list_url() + '?active=0')
        eq_(response.json['meta']['total_count'], 1)
        eq_(response.json['objects'][0]['guid'], inactive.guid)


class TestInAppProductsWithPackagedWebApp(AuthenticatedInAppProductTest):

    def setUp(self):
        super(TestInAppProductsWithPackagedWebApp, self).setUp()
        # Set up a packaged web app, i.e. one without a declared domain.
        self.webapp.update(app_domain=None, is_packaged=True,
                           guid='some-app-guid')
        self.product = self.create_product()

    def marketplace_origin(self):
        return 'marketplace:{}'.format(self.webapp.guid)

    def list_url(self):
        return reverse('in-app-products-list',
                       kwargs={'origin': self.marketplace_origin()})

    def detail_url(self, guid):
        return reverse('in-app-products-detail',
                       kwargs={'origin': self.marketplace_origin(),
                               'guid': guid})

    def test_listing(self):
        response = self.get(self.list_url())
        eq_(response.status_code, status.HTTP_200_OK)
        eq_(response.json['meta']['total_count'], 1)

    def test_details(self):
        res = self.get(self.detail_url(self.product.guid))
        eq_(res.status_code, status.HTTP_200_OK)
        eq_(res.json['app'], self.webapp.app_slug)


class TestInAppProductViewSetUnauthorized(BaseInAppProductViewSetTests):
    fixtures = fixture('user_999', 'webapp_337141', 'prices')

    def setUp(self):
        super(TestInAppProductViewSetUnauthorized, self).setUp()
        self.mock_logo_url()
        user = UserProfile.objects.get(id=999)
        self.client = self.setup_client(user)

    def test_create(self):
        response = self.post(self.list_url(),
                             self.valid_in_app_product_data)
        eq_(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update(self):
        product = self.create_product()
        self.valid_in_app_product_data['name'] = 'Orange Gems'
        response = self.put(self.detail_url(product.guid),
                            self.valid_in_app_product_data)
        eq_(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list(self):
        product1 = self.create_product()
        product2 = self.create_product()
        response = self.get(self.list_url())
        eq_(response.status_code, status.HTTP_200_OK)
        eq_(sorted([p['guid'] for p in response.json['objects']]),
            sorted([product1.guid, product2.guid]))

    def test_fxpay_version_header(self):
        res = self.get(self.list_url())
        eq_(res['Access-Control-Allow-Headers'],
            'content-type, accept, x-fxpay-version')

    def test_detail(self):
        product = self.create_product()
        response = self.get(self.detail_url(product.guid))
        eq_(response.status_code, status.HTTP_200_OK)
        eq_(response.json['guid'], product.guid)

    def test_delete(self):
        product = self.create_product()
        response = self.delete(self.detail_url(product.guid))
        eq_(response.status_code, status.HTTP_403_FORBIDDEN)


class TestInAppProductViewSetAuthorizedCookie(BaseInAppProductViewSetTests):
    fixtures = fixture('user_999', 'webapp_337141', 'prices')

    def setUp(self):
        super(TestInAppProductViewSetAuthorizedCookie, self).setUp()
        self.mock_logo_url()
        user = UserProfile.objects.get(id=31337)
        self.login(user)

    def test_create(self):
        response = self.post(self.list_url(),
                             self.valid_in_app_product_data)
        eq_(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update(self):
        product = self.create_product()
        self.valid_in_app_product_data['name'] = 'Orange Gems'
        response = self.put(self.detail_url(product.guid),
                            self.valid_in_app_product_data)
        eq_(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete(self):
        product = self.create_product()
        response = self.delete(self.detail_url(product.guid))
        eq_(response.status_code, status.HTTP_403_FORBIDDEN)


class TestStubInAppProductViewSet(BaseInAppProductViewSetTests):
    fixtures = fixture('user_999', 'webapp_337141', 'prices2')

    def setUp(self):
        super(TestStubInAppProductViewSet, self).setUp()
        self.mock_logo_url()
        self.client = JSONClient()

    def detail_url(self, guid):
        return reverse('stub-in-app-products-detail',
                       kwargs={'guid': guid})

    def list_url(self):
        return reverse('stub-in-app-products-list')

    def objects(self, res):
        return sorted(res.json['objects'], key=lambda d: d['name'])

    def test_fxpay_version_header(self):
        res = self.get(self.list_url())
        eq_(res['Access-Control-Allow-Headers'],
            'content-type, accept, x-fxpay-version')

    def test_get_when_stubs_dont_exist(self):
        res = self.get(self.list_url())
        eq_(res.status_code, status.HTTP_200_OK)
        objects = self.objects(res)
        eq_(objects[0]['name'], 'Kiwi')
        eq_(objects[0]['price_id'], 1)
        eq_(objects[0]['logo_url'],
            'http://testserver/media/img/developers/simulated-kiwi.png')
        eq_(objects[1]['name'], 'Rocket')
        eq_(objects[1]['price_id'], 2)
        eq_(objects[1]['logo_url'],
            'http://testserver/media/img/mkt/icons/rocket-64.png')

    def test_get_existing_stubs(self):
        stub = InAppProduct.objects.create(stub=True,
                                           name='Test Product',
                                           price=Price.objects.all()[0])
        stub.save()  # generate GUID

        res = self.get(self.list_url())
        eq_(res.status_code, status.HTTP_200_OK)
        objects = self.objects(res)
        eq_(objects[0]['guid'], stub.guid)
        eq_(objects[0]['name'], stub.name)
        eq_(objects[0]['price_id'], stub.price.pk)
        eq_(InAppProduct.objects.all().count(), 1,
            'No new stubs should have been created')

    def test_get_existing_stub_detail(self):
        stub = InAppProduct.objects.create(stub=True,
                                           name='Test Product',
                                           price=Price.objects.all()[0])
        stub.save()  # generate GUID

        res = self.get(self.detail_url(stub.guid))
        eq_(res.status_code, status.HTTP_200_OK)
        eq_(res.json['guid'], stub.guid)
        eq_(res.json['name'], stub.name)
        eq_(res.json['price_id'], stub.price.pk)
